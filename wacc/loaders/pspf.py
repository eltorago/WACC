"""PSPF List of Requirements, from the extracted table.

Reads data/corpus/pspf.json, which tools/extract_pspf.py produces from the published
PDF. The shipped package touches JSON only, so the standard-library rule holds.

The table publishes applicability, mandatory status, start date, scoring and a
retain/modify/retire decision for every requirement. All of that is extracted. The one
thing deliberately not taken at face value is the Mandatory column: it describes
whether the PSPF *reporting question* must be answered, not the force of the
requirement, and conflating the two would misstate an obligation.
"""

import json
import os
import re
from typing import Dict, List, Optional

from ..model import (
    Control,
    Corpus,
    Framework,
    ObligationStrength,
    Origin,
    Provenance,
)

_CEASED = re.compile(r"ceased|retire", re.IGNORECASE)


def _column(columns: List[str], prefix: str) -> Optional[str]:
    for name in columns:
        if name.lower().startswith(prefix.lower()):
            return name
    return None


def load_into(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    columns = data.get("columns", [])
    records = data.get("records", [])
    col_text = _column(columns, "Release") or _column(columns, "Requirement")
    col_appl = _column(columns, "Applicability")
    col_mand = _column(columns, "Question Mandatory")
    col_decision = _column(columns, "Decision")
    col_start = _column(columns, "Start Date")
    col_type = _column(columns, "Question Type")
    col_scored = _column(columns, "Question Scored")
    if not col_text:
        raise ValueError("pspf.json has no requirement text column")

    if data.get("title"):
        framework.revision = data["title"]
        framework.revision_source = "title row of the published table"

    counts = {
        "domains": 0,
        "sections": 0,
        "requirements": 0,
        "ceased": 0,
        "numbering_gaps": [],
    }
    domains: Dict[str, str] = {}
    sections: Dict[str, str] = {}
    numbers: List[int] = []

    for record in records:
        number = str(record.get("req_number", "")).strip()
        text = str(record.get(col_text, "")).strip()
        if not number or not text:
            continue
        numbers.append(int(number))
        domain = str(record.get("Domain", "")).strip()
        section = str(record.get("Section", "")).strip()

        if domain and domain not in domains:
            control = Control(
                framework_key=framework.key,
                identifier=domain,
                title=domain,
                text="",
                depth=0,
                attributes={"structural": True},
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            domains[domain] = control.uid
            counts["domains"] += 1

        section_key = "%s|%s" % (domain, section)
        if section and section_key not in sections:
            control = Control(
                framework_key=framework.key,
                identifier="%s %s" % (domain, section.split(".")[0]),
                title=section,
                text="",
                depth=1,
                parent_uid=domains.get(domain),
                section_ref=domain or None,
                attributes={"structural": True},
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            sections[section_key] = control.uid
            counts["sections"] += 1

        mandatory = str(record.get(col_mand, "")).strip() if col_mand else ""
        decision = str(record.get(col_decision, "")).strip() if col_decision else ""
        ceased = bool(_CEASED.search(mandatory) or _CEASED.search(decision))

        tags: Dict[str, object] = {}
        for column, key in (
            (col_mand, "reporting_question"),
            (col_decision, "release_decision"),
            (col_start, "start_date"),
            (col_type, "question_type"),
            (col_scored, "scoring"),
        ):
            if column:
                value = str(record.get(column, "")).strip()
                if value:
                    tags[key] = value

        # Applicability here is a sentence, not a list of levels the way the ISM's is.
        applicability = str(record.get(col_appl, "")).strip() if col_appl else ""

        control = Control(
            framework_key=framework.key,
            identifier="Req %s" % number,
            title=None,
            text=text,
            depth=2,
            parent_uid=sections.get(section_key) or domains.get(domain),
            section_ref="%s > %s" % (domain, section) if domain and section else None,
            applicability=applicability or None,
            publisher_tags=tags,
            obligation=(
                ObligationStrength.INFORMATIVE if ceased else ObligationStrength.MANDATORY
            ),
            obligation_provenance=Provenance.PUBLISHED,
            attributes={"ceased": True} if ceased else {},
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        counts["requirements"] += 1
        if ceased:
            counts["ceased"] += 1

    if numbers:
        gaps = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        counts["numbering_gaps"] = gaps
        if gaps:
            corpus.load_warnings.append(
                "pspf: requirement numbers are not contiguous — %s absent from the "
                "published table. Nothing downstream may assume a dense range."
                % ", ".join(str(g) for g in gaps)
            )
    return counts
