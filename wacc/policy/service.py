"""One application service for CLI, desktop, saved views and report aggregates."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid

from . import ENGINE_VERSION, SCHEMA_VERSION
from . import alignment, corpus, documents, rules
from .contracts import AUTOMATED, REVIEWED, PolicyError, fingerprint, canonical_payload, validate_run


def now():
    return datetime.now(timezone.utc).isoformat()


def analyse(paths, name="Framework alignment", scope="Selected policy documents", organisation="", framework="wa-csp",
            edition=None, corpus_version=None, also=(), recurse=False, approval="unknown", retention="extracted", cancel=None):
    if not scope.strip() or approval not in ("approved", "draft", "unknown", "superseded") or retention not in ("evidence", "extracted"):
        raise PolicyError("Choose a scope, document approval status and supported retention mode.", 2)
    selected = documents.select(paths, recurse)
    inputs, skipped = documents.expand_inputs(selected)
    baseline = corpus.load(framework, edition, corpus_version, also)
    imported, duplicates = [], []
    seen = set()
    text_length = 0
    for path, member in inputs:
        if cancel and cancel.is_set():
            raise KeyboardInterrupt
        try:
            doc = documents.extract_worker(path, cancel, member=member)
        except PolicyError as error:
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.stat().st_size <= documents.MAX_BYTES else "unhashed-" + hashlib.sha256(str(path).encode()).hexdigest()
            doc = dict(id=digest, sha256=digest, path=str(path), name=path.name, format=path.suffix,
                       status="Failed", warnings=[str(error)], passages=[], parserVersion=documents.PARSER_VERSION)
            if member is not None:
                identifier = 'unhashed-' + hashlib.sha256((digest + '/' + member).encode()).hexdigest()
                doc.update(id=identifier, sha256=identifier, name=path.name + ' / ' + member,
                           format=documents.PurePosixPath(member).suffix.lower(), archiveMember=member, archiveHash=digest)
        if doc["id"] in seen:
            duplicates.append(dict(path=str(path) + (' / ' + member if member else ''), documentId=doc["id"]))
            continue
        seen.add(doc["id"])
        doc.update(approvalStatus=approval, included=approval != "superseded", retention=retention)
        imported.append(doc)
        text_length += sum(len(p['text']) for p in doc['passages'])
        if text_length > 8_000_000:
            raise PolicyError('Selected scope exceeds 8 million extracted characters. Split it into explicitly named assessments.')
    active = [d for d in imported if d["included"]]
    incomplete = not active or any(d["status"] != "Ready" for d in active)
    findings = []
    for req in deepcopy(baseline["requirements"]):
        if cancel and cancel.is_set():
            raise KeyboardInterrupt
        evidence, atom_results = [], []
        for atom in req["obligations"]:
            states = []
            if atom["rule"]:
                # Complete bounded lexical scan; no top-K truncation or cross-sentence joins.
                for doc in active:
                    for passage in doc["passages"]:
                        for trace in rules.evaluate(atom["rule"], passage):
                            state = trace["state"]
                            if state == "Matched" and doc["approvalStatus"] != "approved":
                                state = "Ambiguous"
                            states.append(state)
                            if state == "Missing":
                                continue
                            entry = dict(documentId=doc["id"], documentHash=doc["sha256"], passageId=passage["id"],
                                         obligationId=atom["id"], requirementId=req["id"], excerpt=passage["text"],
                                         locator=passage["locator"], matchedSpans=trace["matchedSpans"], checks=trace["checks"],
                                         ruleVersion=atom["ruleVersion"], corpusVersion=baseline["version"],
                                         state=state, relation="Direct", matchStrength="Strong" if state == "Matched" else "Unknown",
                                         context=trace["context"], limitations=list(doc["warnings"]))
                            entry["id"] = fingerprint(entry)
                            if entry not in evidence:
                                evidence.append(entry)
            atom_state = ("NotAssessed" if not atom["rule"] else "Conflict" if "Contradiction" in states and "Matched" in states
                          else "Ambiguous" if any(s in states for s in ("Ambiguous", "Contradiction"))
                          else "Matched" if "Matched" in states else "Missing")
            atom_results.append(dict(id=atom["id"], state=atom_state))
        states = [a["state"] for a in atom_results]
        matched = states.count("Matched")
        auto = ("NotAssessed" if incomplete or "NotAssessed" in states else "Ambiguous" if any(s in states for s in ("Ambiguous", "Conflict"))
                else "FullCandidate" if matched == len(states) else "PartialCandidate" if matched else "NoEvidenceFound")
        flags = (["IncompleteExtraction"] if incomplete else []) + (["Conflict"] if "Conflict" in states else [])
        if any(a["rule"] and a['reviewStatus'] != 'HumanApproved' for a in req["obligations"]):
            flags.append("DraftRulesRequireHumanApproval")
        req.update(automatedFinding=auto, applicability="InScope", reviewState="Pending", reviewerFinding=None,
                   atomResults=atom_results, evidence=evidence, flags=flags,
                   candidateProportion=None if auto in ("NotAssessed", "Ambiguous") else matched / len(states),
                   missingObligations=[a["id"] for a in atom_results if a["state"] != "Matched"])
        findings.append(req)
    aligned = alignment.compare(findings, imported, cancel)
    for row in findings:
        row['alignment'] = aligned[row['id']]
    if retention == "evidence":
        kept = {e["passageId"] for r in findings for e in r["evidence"]}
        kept.update(m['passageId'] for result in aligned.values() for m in result['matches'])
        for doc in imported:
            doc["extractedPassageCount"] = len(doc["passages"])
            doc["passages"] = [p for p in doc["passages"] if p["id"] in kept]
    run = dict(schemaVersion=SCHEMA_VERSION, runId=str(uuid.uuid4()), createdAt=now(),
               name=name, organisation=organisation, scope=dict(description=scope, mode="SingleDocument" if len(imported)==1 else "PolicySet",
               selectedDocumentIds=[d["id"] for d in imported], duplicates=duplicates, retention=retention, skippedInputs=skipped),
               versions=dict(engine=ENGINE_VERSION, corpus=baseline["version"], frameworks=baseline["frameworks"],
                             rulesHash=baseline["rulesHash"], normaliser=documents.NORMALISER_VERSION,
                             retrieval="complete-same-sentence-lexical-scan-1", parser=documents.PARSER_VERSION, alignment=alignment.VERSION),
               documents=imported, requirements=findings, mappings=baseline["mappings"],
               limitations=(["Some selected documents could not be fully read. Unmatched requirements are marked Unable to check."] if incomplete else []),
               canonicalHash="")
    run["canonicalHash"] = fingerprint(canonical_payload(run))
    validate_run(run)
    return run


def apply_reviews(run, events):
    rows = deepcopy(run["requirements"])
    latest = {e["requirementId"]: e for e in events if e["runId"] == run["runId"]}
    previous = {e["requirementId"] for e in events if e["runId"] != run["runId"]}
    for row in rows:
        event = latest.get(row["id"])
        if event:
            row.update(reviewState="Reviewed", reviewerFinding=event["finding"], review=deepcopy(event))
            row["applicability"] = "NotApplicable" if event["finding"] == "NotApplicable" else "InScope"
        elif row["id"] in previous:
            row["reviewState"] = "NeedsReReview"
    return rows


def summary(run, events=(), framework=None):
    rows = apply_reviews(run, events)
    if framework is not None:
        rows = [r for r in rows if r['frameworkId'] == framework]
    return summarise_rows(rows)


def summarise_rows(rows):
    """Aggregate an already reviewed view without copying its evidence again."""
    active = [r for r in rows if r["applicability"] != "NotApplicable"]
    computed = [r for r in active if r["candidateProportion"] is not None]
    numerator = sum(r["candidateProportion"] for r in computed)
    confirmed = sum(len(r.get("review", {}).get("confirmedObligations", [])) / len(r["obligations"]) for r in active)
    n = len(active)
    return dict(inScope=n, excluded=len(rows)-n, computable=len(computed), unassessed=n-len(computed),
                automatedCounts={s: sum(r["automatedFinding"] == s for r in active) for s in AUTOMATED},
                reviewed=sum(r["reviewState"] == "Reviewed" for r in rows), reviewable=len(rows),
                reviewerCounts={s: sum(r['reviewerFinding'] == s and r['reviewState'] == 'Reviewed' for r in rows) for s in REVIEWED},
                assessedScopeCoverage=dict(numerator=numerator, denominator=len(computed), percent=100*numerator/len(computed) if computed else None),
                assessmentCompleteness=dict(numerator=len(computed), denominator=n, percent=100*len(computed)/n if n else None),
                confirmedEvidenceFloor=dict(numerator=confirmed, denominator=n, percent=100*confirmed/n if n else None))


def framework_summaries(run, events=()):
    return summarise_frameworks(run['versions']['frameworks'], apply_reviews(run, events))


def summarise_frameworks(frameworks, rows):
    grouped = {f['id']: [] for f in frameworks}
    for row in rows:
        grouped[row['frameworkId']].append(row)
    return [dict(id=f['id'], title=f['title'], edition=f['edition'], **summarise_rows(grouped[f['id']]))
            for f in frameworks]


def review_event(run, requirement_id, finding, reason, reviewer, confirmed=(), evidence_ids=(), comment="", manual_evidence=()):
    row = next((r for r in run["requirements"] if r["id"] == requirement_id), None)
    if not row or finding not in REVIEWED or not reason.strip() or not reviewer.strip():
        raise PolicyError("Select a requirement and finding; provide a reviewer name and reason.", 2)
    atoms = {a["id"] for a in row["obligations"]}
    manual = []
    for link in manual_evidence:
        doc = next((d for d in run['documents'] if d['id'] == link['documentId'] and d['included']), None)
        passage = next((p for p in doc['passages'] if p['id'] == link['passageId']), None) if doc else None
        if not passage or link['obligationId'] not in atoms:
            raise PolicyError('Manual evidence must refer to a retained passage and an obligation in this requirement.', 2)
        record = dict(documentId=doc['id'], documentHash=doc['sha256'], passageId=passage['id'],
                      obligationId=link['obligationId'], excerpt=passage['text'], locator=passage['locator'],
                      relation='Direct', provenance='Reviewer-linked evidence')
        record['id'] = fingerprint(record)
        manual.append(record)
    if not set(confirmed) <= atoms or not set(evidence_ids) <= {e["id"] for e in row["evidence"]}:
        raise PolicyError("Review refers to an unknown obligation or evidence record.", 2)
    supported = {e['obligationId'] for e in row['evidence'] if e['id'] in evidence_ids} | {e['obligationId'] for e in manual}
    if not set(confirmed) <= supported:
        raise PolicyError('Each confirmed obligation needs selected or manually linked source evidence.', 2)
    if finding == "Covered" and set(confirmed) != atoms:
        raise PolicyError("Covered requires confirmation of every obligation.", 2)
    if finding == "PartiallyCovered" and not 0 < len(set(confirmed)) < len(atoms):
        raise PolicyError("Partial coverage requires some, but not all, obligations.", 2)
    if finding in ("NotCovered", "NotAssessed", "NotApplicable") and confirmed:
        raise PolicyError("This finding cannot confirm obligations.", 2)
    return dict(id=str(uuid.uuid4()), runId=run["runId"], requirementId=requirement_id, finding=finding,
                reason=reason, reviewer=reviewer, identitySource="Local self-declared name", timestamp=now(),
                confirmedObligations=sorted(set(confirmed)), selectedEvidence=sorted(set(evidence_ids)),
                manualEvidence=manual, comment=comment)


def neighbourhood(run, requirement_id, limit=50):
    limit = max(1, min(int(limit), 100))
    edges = [m for m in run["mappings"] if requirement_id in (m["source"], m["target"])]
    rows = next((r for r in run["requirements"] if r["id"] == requirement_id), None)
    if not rows:
        raise PolicyError("Requirement is not in this assessment.")
    edges += [dict(source=e["passageId"], target=e["obligationId"], relationship="candidateEvidenceFor", relation=e["relation"]) for e in rows["evidence"]]
    edges += [dict(source=a["id"], target=requirement_id, relationship="partOf", relation="Hierarchy") for a in rows["obligations"]]
    return dict(edges=edges[:limit], truncated=len(edges)>limit, total=len(edges))
