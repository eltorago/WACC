"""OAG WA better practice guides.

Reads the JSON that tools/extract_oag.py produces.

Both guides load as one framework, with the report number as an attribute. A reader
wants one OAG column showing what the Auditor General expects, not a column per report.

Obligation strength is recommended, not mandatory. These guides state what good looks
like; the Auditor General audits against them but they bind nobody. Reading 'entities
should' as a requirement would overstate the finding, which is the failure this tool
exists to avoid.
"""

import json
from typing import Dict, List

from ..model import (
    Control,
    Corpus,
    Framework,
    Licence,
    ObligationStrength,
    Origin,
    Provenance,
)


def load_into(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    counts = {"guides": 0, "sections": 0, "recommendations": 0, "licences": []}
    licences: List[str] = []

    for guide in data.get("guides", []):
        report = str(guide.get("report", "")).strip()
        guide_uid = None
        if report:
            control = Control(
                framework_key=framework.key,
                identifier=report.split(":")[0].strip(),
                title=str(guide.get("title", "")) or None,
                text="",
                depth=0,
                attributes={
                    "structural": True,
                    "report": report,
                    "published": guide.get("published"),
                    "source_file": guide.get("source_file"),
                },
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            guide_uid = control.uid
            counts["guides"] += 1

        licence = str(guide.get("licence", "")).strip()
        if licence:
            licences.append(licence)

        section_uids: Dict[str, str] = {}
        for record in guide.get("records", []):
            section_number = str(record.get("section_number", "")).strip()
            section_title = str(record.get("section_title", "")).strip()
            prefix = str(record.get("identifier", "")).split()[0]

            section_key = "%s %s" % (prefix, section_number)
            if section_number and section_key not in section_uids:
                control = Control(
                    framework_key=framework.key,
                    identifier=section_key,
                    title=section_title or None,
                    text="",
                    depth=1,
                    parent_uid=guide_uid,
                    section_ref=report or None,
                    attributes={"structural": True},
                    obligation=ObligationStrength.INFORMATIVE,
                    origin=Origin.GENERATED,
                )
                corpus.add_control(control)
                section_uids[section_key] = control.uid
                counts["sections"] += 1

            text = str(record.get("text", "")).strip()
            if not text:
                continue
            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    identifier=str(record.get("identifier")),
                    title=str(record.get("heading", "")).strip() or None,
                    text=text,
                    depth=2,
                    parent_uid=section_uids.get(section_key),
                    section_ref="%s > %s" % (report, section_title) if report else section_title,
                    publisher_tags={"report": report} if report else {},
                    attributes={"page": record.get("page")},
                    obligation=ObligationStrength.RECOMMENDED,
                    obligation_provenance=Provenance.DERIVED,
                    origin=Origin.GENERATED,
                )
            )
            counts["recommendations"] += 1

    counts["licences"] = licences
    _apply_licence(corpus, framework, licences)
    return counts


def _apply_licence(corpus: Corpus, framework: Framework, licences: List[str]) -> None:
    """Set the licence from what the documents say, not from what WA usually does.

    Both guides carry a copyright page permitting reproduction in whole or in part
    provided the source is acknowledged, so the text ships with attribution. That was
    read off the file rather than assumed, which is why the registry started this
    framework as import-only.
    """
    if not licences:
        corpus.load_warnings.append(
            "oag-wa: no copyright statement found in either guide; framework stays "
            "import-only and no OAG text will ship"
        )
        return
    permissive = [l for l in licences if "reproduced in whole or in part" in l.lower()]
    if len(permissive) == len(licences):
        framework.licence = Licence.SHIPPABLE
        framework.notes.append(
            "Licence read from the copyright page of each guide: reproduction in whole "
            "or in part is permitted where the source is acknowledged. Exports carry "
            "the attribution."
        )
    else:
        corpus.load_warnings.append(
            "oag-wa: %d of %d guides state a permissive reproduction licence; the "
            "framework stays import-only until all of them do"
            % (len(permissive), len(licences))
        )
