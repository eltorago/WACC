"""AESCSF Framework Core from AEMO's workbook.

Import only. AEMO's practice text never ships, and the packaging test fails the build
if it would.

The workbook publishes an Australian References column naming ISM controls by number.
That is AEMO asserting the crosswalk, so the links are published rather than derived —
one of the places where the publisher's own answer was sitting in a file.

Two granularities are kept because an assessment is performed at practice level and
reported at domain level.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..io.xlsx import Workbook
from ..model import (
    Control,
    Corpus,
    Framework,
    Link,
    Origin,
    Provenance,
    normalise_identifier,
)

_ISM_REF = re.compile(r"Security Control:\s*(ISM-\d+)", re.IGNORECASE)
_E8_FIELD = re.compile(r"Essential Eight:\s*([^-\n]+?)(?:\s+-\s|$)", re.IGNORECASE)


def parse_australian_references(cell: str) -> List[Tuple[str, Optional[str]]]:
    """Return (ISM identifier, Essential Eight value) for each reference block.

    The cell embeds the ISM control text as it read when AESCSF was published. That
    text is deliberately discarded — the link is by identifier, so it resolves to the
    ISM revision actually loaded rather than to a frozen copy that has since changed.
    """
    out: List[Tuple[str, Optional[str]]] = []
    for block in re.split(r"\n\s*\n", cell or ""):
        block = block.strip()
        if not block:
            continue
        m = _ISM_REF.search(block)
        if not m:
            continue
        e8 = _E8_FIELD.search(block)
        value = e8.group(1).strip() if e8 else None
        if value and value.upper().startswith("N/A"):
            value = None
        out.append((m.group(1), value))
    return out


def load_into(corpus: Corpus, framework: Framework, path: str) -> Dict[str, int]:
    wb = Workbook(path)
    sheet_name = wb.sheet_names[0]
    framework.revision = sheet_name.strip()
    framework.revision_source = "workbook sheet name, the only version this file states"
    header, body = wb.table(sheet_name)
    idx = {name: i for i, name in enumerate(header)}
    required = [
        "Domain",
        "Objective ID",
        "Objective",
        "Practice ID",
        "Practice",
        "Maturity Indicator Level",
        "Security Profile",
        "Australian References",
    ]
    missing = [c for c in required if c not in idx]
    if missing:
        raise ValueError("AESCSF workbook is missing columns: %s" % ", ".join(missing))

    counts = {"domains": 0, "objectives": 0, "practices": 0, "ism_links": 0, "e8_tags": 0}
    seen_domains: Dict[str, str] = {}
    seen_objectives: Dict[str, str] = {}
    pending: List[Tuple[str, str, Optional[str]]] = []

    for row in body:
        domain = row[idx["Domain"]].strip()
        objective_id = row[idx["Objective ID"]].strip()
        objective = row[idx["Objective"]].strip()
        practice_id = row[idx["Practice ID"]].strip()
        practice = row[idx["Practice"]].strip()
        if not practice_id or not practice:
            continue

        if domain and domain not in seen_domains:
            c = Control(
                framework_key=framework.key,
                identifier=domain,
                title=domain.title(),
                text="",
                depth=0,
                attributes={"structural": True},
                origin=Origin.GENERATED,
            )
            corpus.add_control(c)
            seen_domains[domain] = c.uid
            counts["domains"] += 1

        if objective_id and objective_id not in seen_objectives:
            c = Control(
                framework_key=framework.key,
                identifier=objective_id,
                title=None,
                text=objective,
                depth=1,
                parent_uid=seen_domains.get(domain),
                section_ref=domain or None,
                origin=Origin.GENERATED,
            )
            corpus.add_control(c)
            seen_objectives[objective_id] = c.uid
            counts["objectives"] += 1

        tags: Dict[str, object] = {}
        mil = row[idx["Maturity Indicator Level"]].strip()
        profile = row[idx["Security Profile"]].strip()
        if mil:
            tags["maturity_indicator_level"] = mil
        if profile:
            tags["security_profile"] = profile

        attributes: Dict[str, object] = {}
        if "Context and Guidance" in idx:
            guidance = row[idx["Context and Guidance"]].strip()
            if guidance:
                attributes["guidance"] = guidance

        control = Control(
            framework_key=framework.key,
            identifier=practice_id,
            title=None,
            text=practice,
            depth=2,
            parent_uid=seen_objectives.get(objective_id),
            section_ref="%s > %s" % (domain, objective_id) if domain else objective_id,
            publisher_tags=tags,
            attributes=attributes,
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        counts["practices"] += 1

        for ism_id, e8 in parse_australian_references(row[idx["Australian References"]]):
            pending.append((control.uid, ism_id, e8))

    counts["ism_links"], counts["e8_tags"] = _attach_ism(corpus, pending)
    return counts


def _attach_ism(
    corpus: Corpus, pending: List[Tuple[str, str, Optional[str]]]
) -> Tuple[int, int]:
    index = {
        c.identifier_key: uid
        for uid, c in corpus.controls.items()
        if c.framework_key == "ism"
    }
    links = tags = 0
    unresolved: List[str] = []
    for source_uid, ism_id, e8 in pending:
        target_uid = index.get(normalise_identifier(ism_id))
        if target_uid is None:
            unresolved.append(ism_id)
            continue
        corpus.add_link(
            Link(
                source_uid=source_uid,
                target_uid=target_uid,
                provenance=Provenance.PUBLISHED,
                basis="AESCSF Framework Core, Australian References column",
                asserted_by="AEMO",
            )
        )
        links += 1
        if e8:
            control = corpus.controls[source_uid]
            existing = control.tag_list("essential_eight_strategy")
            if e8 not in existing:
                existing.append(e8)
                control.publisher_tags["essential_eight_strategy"] = existing
                tags += 1

    if unresolved:
        distinct = sorted(set(unresolved))
        corpus.load_warnings.append(
            "aescsf: %d references name ISM controls not in the loaded ISM (%d "
            "distinct, e.g. %s). AESCSF cites the revision current when it was "
            "published; these have since been retired."
            % (len(unresolved), len(distinct), ", ".join(distinct[:5]))
        )
    return links, tags
