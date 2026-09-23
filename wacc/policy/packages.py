"""Signed data-only corpus archives. Trust keys belong to the installed application."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from .contracts import PolicyError, canonical
from .documents import checked_archive, local_file
from .rules import validate_rule

TRUST_FILE = Path(__file__).resolve().parents[2] / "packaging/trusted-corpus-keys.json"


def installation_root():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share"))) / "WACC/corpus"


def validate_corpus(data):
    if not isinstance(data, dict) or set(data) != {"version", "frameworks", "requirements", "mappings", "rulesHash", "status"}:
        raise PolicyError("Invalid corpus contract.", 5)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", data["version"]):
        raise PolicyError("Invalid corpus version.", 5)
    if not 1 <= len(data["frameworks"]) <= 100 or not 1 <= len(data["requirements"]) <= 20000 or len(data["mappings"]) > 100000:
        raise PolicyError("Corpus exceeds supported limits.", 5)
    frameworks = {f["id"] for f in data["frameworks"]}
    seen = set()
    for r in data["requirements"]:
        if not {"id", "frameworkId", "officialReference", "heading", "parentId", "authoritativeText", "context", "sourceLocator", "obligations"} <= r.keys() or r["id"] in seen or r["frameworkId"] not in frameworks:
            raise PolicyError("Invalid requirement reference.", 5)
        seen.add(r["id"])
        if not 1 <= len(r["obligations"]) <= 50:
            raise PolicyError("Invalid obligation count.", 5)
        for a in r["obligations"]:
            if a.get("rule"):
                if a.get("reviewStatus") != "HumanApproved":
                    raise PolicyError("A release rule lacks human approval provenance.", 5)
                validate_rule(a["rule"])
    for m in data["mappings"]:
        if m["source"] not in seen or m["target"] not in seen or m["relation"] != "MappedOnly":
            raise PolicyError("Invalid corpus relationship.", 5)
    from .contracts import fingerprint
    if data["rulesHash"] != fingerprint([r["obligations"] for r in data["requirements"]]):
        raise PolicyError("Corpus rule digest mismatch.", 5)


def verify(path, include_data=False):
    try:
        path = local_file(path)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise PolicyError("Corpus archive is too large.", 5)
        with checked_archive(path.read_bytes()) as archive:
            if set(archive.namelist()) != {"manifest.json", "corpus.json", "signature.json"}:
                raise PolicyError("Corpus package contains missing or unlisted files.", 5)
            raw = archive.read("manifest.json")
            manifest = json.loads(raw)
            signature = json.loads(archive.read("signature.json"))
            trust = json.loads(TRUST_FILE.read_text(encoding="utf-8")) if TRUST_FILE.is_file() else {"keys": {}}
            key = trust["keys"].get(signature["keyId"])
            if not key or key.get("revoked") or signature.get("algorithm") != "Ed25519":
                raise PolicyError("No approved signing key is installed for this corpus.", 5)
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(base64.b64decode(key["publicKey"], validate=True)).verify(base64.b64decode(signature["signature"], validate=True), raw)
            payload = archive.read("corpus.json")
            if set(manifest) != {"schemaVersion", "version", "engineMajor", "files", "reviewRecord"} or manifest["schemaVersion"] != "1.0" or manifest["engineMajor"] != 0:
                raise PolicyError("Corpus schema or engine version is incompatible.", 5)
            if manifest["files"] != {"corpus.json": hashlib.sha256(payload).hexdigest()}:
                raise PolicyError("Corpus payload digest mismatch.", 5)
            data = json.loads(payload)
            validate_corpus(data)
            if data["version"] != manifest["version"] or not manifest["reviewRecord"]:
                raise PolicyError("Corpus version or review provenance is missing.", 5)
            result = dict(version=manifest["version"], signer=signature["keyId"], sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            return (result, data) if include_data else result
    except PolicyError as error:
        raise PolicyError(str(error), 5)
    except Exception:
        raise PolicyError("Corpus signature or data validation failed.", 5)


def install(path):
    metadata = verify(path)
    root = installation_root()
    root.mkdir(parents=True, exist_ok=True)
    target = root / (metadata["version"] + ".waccpack")
    if target.exists():
        if verify(target)["sha256"] == metadata["sha256"]:
            return metadata
        raise PolicyError("This corpus version is already installed with different bytes.", 5)
    stage = root / (uuid.uuid4().hex + ".tmp")
    try:
        shutil.copyfile(path, stage)
        verify(stage)
        # Publish only the completely written file, without replacing any existing version.
        os.link(stage, target)
    finally:
        if stage.exists():
            stage.unlink()
    return metadata


def installed(version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise PolicyError("Invalid corpus version.", 5)
    return verify(installation_root() / (version + ".waccpack"), True)[1]
