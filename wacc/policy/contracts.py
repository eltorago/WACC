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
    passages = {(d['id'], p['id']): p for d in run['documents'] for p in d['passages']}
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
            passage = passages.get((doc['id'], evidence['passageId']))
            if passage is None or evidence["excerpt"] != passage["text"]:
                raise PolicyError("Evidence excerpt does not match its recorded passage.")
            for span in evidence["matchedSpans"]:
                if not 0 <= span["start"] < span["end"] <= len(passage["text"]):
                    raise PolicyError("Invalid evidence source span.")
        if 'alignment' in req:
            result = req['alignment']
            if result['status'] not in ('Mentioned', 'Related wording', 'Not mentioned', 'Unable to check') or len(result['matches']) > 5:
                raise PolicyError('Invalid framework alignment result.')
            if result['method'] != run['versions'].get('alignment'):
                raise PolicyError('Alignment method does not match the saved version.')
            for match in result['matches']:
                doc = documents.get(match['documentId'])
                passage = passages.get((match['documentId'], match['passageId']))
                if not doc or not passage or match['documentHash'] != doc['sha256']:
                    raise PolicyError('Alignment passage does not match its recorded source.')
                if not 0 <= match['start'] < match['end'] <= len(passage['text']):
                    raise PolicyError('Invalid alignment passage range.')
                if match['excerpt'] != passage['text'][match['start']:match['end']]:
                    raise PolicyError('Alignment excerpt does not match its source range.')
                for span in match['matchedSpans']:
                    if not 0 <= span['start'] < span['end'] <= len(match['excerpt']):
                        raise PolicyError('Invalid alignment source span.')
    expected = canonical_payload(run)
    if fingerprint(expected) != run["canonicalHash"]:
        raise PolicyError("Saved analysis content does not match its recorded digest.")


def canonical_payload(run):
    return {key: run[key] for key in ("schemaVersion", "versions", "scope", "documents", "requirements", "mappings")}
