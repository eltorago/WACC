"""WA Government Cyber Security Policy and Premier's Circular 2025/13.

Reads the JSON that tools/extract_wa_csp.py and tools/extract_wa_circular.py produce.

The 2026 policy names NIST CSF as an alignment source. Function-level links match
its six published function names to CSF 2.0; they do not map individual requirements.
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
from ..wa_policy import SOURCE_SHA256


def _load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_policy(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    data = _load(path)
    if data.get('edition') != '2026' or data.get('source_sha256') != SOURCE_SHA256:
        raise ValueError('Re-extract the reviewed 2026 WA CSP before loading its requirements.')
    framework.revision = data.get("title") or framework.revision
    framework.revision_source = "title page of the policy"
    return _load_2026(corpus, framework, data)


def _load_2026(corpus, framework, data):
    """Keep nested clauses under their actual section, including 3.1 and 3.14."""
    by_section = {}
    for record in data['records']:
        by_section.setdefault(record['section_number'], []).append(record)
    counts = dict(functions=6, sections=0, requirements=len(data['records']), csf_links=0)
    for number, title in data['contents_sections'].items():
        rows = by_section.get(number, [])
        standalone = next((r for r in rows if r['identifier'] == number), None)
        text = standalone['text'] if standalone else (rows[0].get('lead_in', '') if rows else '')
        parent = number.rpartition('.')[0]
        attributes = dict(edition='2026', source_page=rows[0]['page'] if rows else None)
        if not standalone and not text:
            attributes['structural'] = True
        if data['section_notes'].get(number):
            attributes['source_notes'] = data['section_notes'][number]
        corpus.add_control(Control(framework_key=framework.key, identifier=number, title=title,
            text=text, depth=number.count('.'), parent_uid=framework.key + ':' + parent if parent else None,
            attributes=attributes, obligation=obligation_of(text), obligation_provenance=Provenance.DERIVED,
            origin=Origin.GENERATED))
        if parent:
            counts['sections'] += 1
        for record in rows:
            if record['identifier'] == number:
                continue
            context = record.get('lead_in', '')
            corpus.add_control(Control(framework_key=framework.key, identifier=record['identifier'],
                text=record['text'], depth=number.count('.') + 1, parent_uid=framework.key + ':' + number,
                section_ref=number + ' ' + title,
                attributes=dict(edition='2026', source_page=record['page'], source_context=context),
                obligation=obligation_of(context + ' ' + record['text']),
                obligation_provenance=Provenance.DERIVED, origin=Origin.GENERATED))
    counts['csf_links'] = _link_functions_to_csf(corpus, framework, data)
    return counts


def _link_functions_to_csf(
    corpus: Corpus, framework: Framework, data: dict
) -> int:
    """Match the Policy's six function names to CSF 2.0's.

    Nothing here reads the two structures as equivalent below function level. The
    Policy's 3.5 Data Offshoring has no CSF counterpart, and pretending
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
                    "the Policy states its requirements are aligned with NIST CSF "
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
