"""WA Government Cyber Security Policy and Premier's Circular 2025/13.

Reads the JSON that tools/extract_wa_csp.py and tools/extract_wa_circular.py produce.

The Policy states its own alignment — "The requirements of this Policy are aligned with
the advice from the Australian Cyber Security Centre (ACSC) and the Cyber Security
Framework developed by the United States NIST 2.0" — and then organises itself under
the six CSF 2.0 function names. DGov asserts the alignment and NIST names the
functions, so the function-level links are published-tag, with the name match called
out as this tool's.
"""

import json
from typing import Dict, List, Optional

from ..model import (
    Control,
    Corpus,
    Framework,
    Link,
    LinkKind,
    ObligationStrength,
    Origin,
    Provenance,
)
from .legislation import obligation_of


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_policy(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    data = _load(path)
    framework.revision = data.get("title") or framework.revision
    framework.revision_source = "title page of the policy"

    counts = {"functions": 0, "sections": 0, "requirements": 0, "csf_links": 0}
    function_uids: Dict[str, str] = {}
    section_uids: Dict[str, str] = {}

    for number, title in sorted(data.get("functions", {}).items()):
        control = Control(
            framework_key=framework.key,
            identifier=number,
            title=title,
            text="",
            depth=0,
            attributes={"structural": True},
            obligation=ObligationStrength.INFORMATIVE,
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        function_uids[number] = control.uid
        counts["functions"] += 1

    for record in data.get("records", []):
        section_number = str(record.get("section_number", ""))
        section_title = str(record.get("section_title", ""))
        function = section_number.split(".")[0]

        if section_number and section_number not in section_uids:
            control = Control(
                framework_key=framework.key,
                identifier=section_number,
                title=section_title or None,
                text=str(record.get("lead_in", "")),
                depth=1,
                parent_uid=function_uids.get(function),
                section_ref=data.get("functions", {}).get(function),
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            section_uids[section_number] = control.uid
            counts["sections"] += 1

        text = str(record.get("text", "")).strip()
        if not text:
            continue
        identifier = str(record.get("identifier"))
        if identifier == section_number:
            # Sections such as 1.6 Secure Device Disposal Governance state their
            # requirement in one sentence with no lettered items. Skipping the record
            # to avoid duplicating the section container silently deleted the
            # requirement, so a search for secure disposal found nothing in the WA CSP.
            container = corpus.control(section_uids.get(section_number, ""))
            if container is not None:
                container.text = text
                container.obligation = obligation_of(text)
                container.obligation_provenance = Provenance.DERIVED
                container.attributes.pop("structural", None)
                counts["requirements"] += 1
            continue

        lead_in = str(record.get("lead_in", ""))
        control = Control(
            framework_key=framework.key,
            identifier=identifier,
            title=None,
            text=text,
            depth=2,
            parent_uid=section_uids.get(section_number),
            section_ref="%s %s" % (section_number, section_title) if section_title else None,
            attributes={"lead_in": lead_in} if lead_in else {},
            obligation=obligation_of("%s %s" % (lead_in, text)),
            obligation_provenance=Provenance.DERIVED,
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        counts["requirements"] += 1

    counts["csf_links"] = _link_functions_to_csf(corpus, framework, data)
    return counts


def _link_functions_to_csf(
    corpus: Corpus, framework: Framework, data: dict
) -> int:
    """Match the Policy's six function names to CSF 2.0's.

    Nothing here reads the two structures as equivalent below function level. The
    Policy's 1.5 Data Offshoring Governance has no CSF counterpart, and pretending
    otherwise at section level would manufacture coverage.
    """
    csf_functions = {
        (c.title or "").strip().lower(): c.uid
        for c in corpus.controls_for("csf")
        if c.depth == 0
    }
    if not csf_functions:
        return 0

    linked = 0
    for number, title in data.get("functions", {}).items():
        target = csf_functions.get(title.strip().lower())
        source = corpus.control("%s:%s" % (framework.key, number))
        if not target or source is None:
            continue
        corpus.add_link(
            Link(
                source_uid=source.uid,
                target_uid=target,
                provenance=Provenance.PUBLISHED_TAG,
                basis=(
                    "the Policy states its requirements are aligned with NIST CSF 2.0 "
                    "and organises them under the same six function names"
                ),
                kind=LinkKind.ALIGNS_WITH,
                tag_side=(
                    "both ends published; matching the two on function name is this "
                    "tool's, and it holds at function level only"
                ),
            )
        )
        linked += 1
    return linked


def load_circular(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    data = _load(path)
    fields = data.get("fields", {})
    if fields.get("Number"):
        framework.revision = "Circular %s, issued %s" % (
            fields["Number"],
            fields.get("Issue Date", "date not stated"),
        )
        framework.revision_source = "header fields of the circular"

    counts = {"measures": 0, "requirements": 0, "informative": 0}
    measure_uids: Dict[str, str] = {}

    for measure in data.get("measures", []):
        number = str(measure["number"])
        control = Control(
            framework_key=framework.key,
            identifier=number,
            title=str(measure["heading"]).rstrip("."),
            text="",
            depth=0,
            attributes={"structural": True},
            obligation=ObligationStrength.INFORMATIVE,
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        measure_uids[number] = control.uid
        counts["measures"] += 1

    for record in data.get("records", []):
        text = str(record.get("text", "")).strip()
        if not text:
            continue
        lead_in = str(record.get("lead_in", ""))
        # The obligation can sit in the introducing bullet rather than the item, so
        # 'Entities must:' followed by 'Implement the Policy' is read as one statement.
        obligation = obligation_of("%s %s" % (lead_in, text))
        control = Control(
            framework_key=framework.key,
            identifier=str(record.get("identifier")),
            title=None,
            text=text,
            depth=1,
            parent_uid=measure_uids.get(str(record.get("measure"))),
            section_ref=str(record.get("measure_heading", "")).rstrip(".") or None,
            attributes={"lead_in": lead_in} if lead_in else {},
            obligation=obligation,
            obligation_provenance=Provenance.DERIVED,
            origin=Origin.GENERATED,
        )
        corpus.add_control(control)
        counts["requirements"] += 1
        if obligation is ObligationStrength.INFORMATIVE:
            counts["informative"] += 1
    return counts
