"""Shared JSON contracts and bounded validation for untrusted saved assessments."""
import hashlib
import json

from . import ENGINE_VERSION, SCHEMA_VERSION

AUTOMATED = ("FullCandidate", "PartialCandidate", "NoEvidenceFound", "Ambiguous", "NotAssessed")
REVIEWED = ("Covered", "PartiallyCovered", "NotCovered", "NotAssessed", "NotApplicable")


class PolicyError(Exception):
    def __init__(self, message, code=3):
        super().__init__(message)
        self.code = code


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def envelope(operation, **values):
    return dict(schemaVersion=SCHEMA_VERSION, operation=operation, status="Completed",
                warnings=[], errors=[], **values)


def validate_run(run):
    required = {"schemaVersion", "runId", "versions", "scope", "documents", "requirements", "mappings", "canonicalHash"}
    if not isinstance(run, dict) or not required <= run.keys() or run["schemaVersion"] != SCHEMA_VERSION:
        raise PolicyError("Unsupported or incomplete assessment contract.")
    if len(run["requirements"]) > 20000 or len(run["documents"]) > 250:
        raise PolicyError("Assessment exceeds supported record limits.")
    documents = {d["id"]: d for d in run["documents"]}
    requirements = set()
    for req in run["requirements"]:
        if req["id"] in requirements or req["automatedFinding"] not in AUTOMATED:
            raise PolicyError("Invalid or duplicate requirement finding.")
        requirements.add(req["id"])
        atoms = {a["id"] for a in req["obligations"]}
        for evidence in req["evidence"]:
            doc = documents.get(evidence["documentId"])
            if not doc or evidence["obligationId"] not in atoms or evidence["documentHash"] != doc["sha256"]:
                raise PolicyError("Evidence references an unknown source or obligation.")
            passage = next((p for p in doc["passages"] if p["id"] == evidence["passageId"]), None)
            if passage is None or evidence["excerpt"] != passage["text"]:
                raise PolicyError("Evidence excerpt does not match its recorded passage.")
            for span in evidence["matchedSpans"]:
                if not 0 <= span["start"] < span["end"] <= len(passage["text"]):
                    raise PolicyError("Invalid evidence source span.")
    expected = canonical_payload(run)
    if fingerprint(expected) != run["canonicalHash"]:
        raise PolicyError("Saved analysis content does not match its recorded digest.")


def canonical_payload(run):
    return {key: run[key] for key in ("schemaVersion", "versions", "scope", "documents", "requirements", "mappings")}
