"""Tier-5 technical specifications, loaded from curated extracts.

Every tier-5 corpus arrives the same way: a list of normative statements, each with the
section reference it can be cited by and the parameters it states. The extractors that
produce those lists differ per document; this loader does not care which one ran.

Obligation strength here is published rather than derived. NIST writes SHALL, SHOULD
and SHALL NOT as RFC 2119 keywords, so the strength is the publisher's own word and not
this tool's reading of tone.
"""

import json
from typing import Dict, List, Optional

from ..model import (
    Control,
    Corpus,
    Framework,
    ObligationStrength,
    Origin,
    Provenance,
)

# RFC 2119 keywords, which every one of these publications uses deliberately.
OBLIGATION_BY_KEYWORD = {
    "SHALL": ObligationStrength.MANDATORY,
    "MUST": ObligationStrength.MANDATORY,
    "SHALL NOT": ObligationStrength.PROHIBITED,
    "MUST NOT": ObligationStrength.PROHIBITED,
    "SHOULD": ObligationStrength.RECOMMENDED,
    "SHOULD NOT": ObligationStrength.DISCOURAGED,
    "MAY": ObligationStrength.PERMITTED,
}


def load_groups(
    corpus: Corpus,
    framework: Framework,
    groups: List[Dict[str, object]],
    group_label: str = "volume",
) -> Dict[str, object]:
    """Load grouped statements as a three-level framework.

    Group, then section, then the statement itself. A statement is the citable unit,
    so its identifier carries the section reference and its position within it.
    """
    counts = {
        "groups": 0,
        "sections": 0,
        "statements": 0,
        "parameters": {},
        "obligations": {},
    }
    parameters: Dict[str, int] = {}
    obligations: Dict[str, int] = {}

    for group in groups:
        key = str(group.get(group_label) or group.get("key") or "").strip()
        title = str(group.get("title", "")).strip()
        group_uid: Optional[str] = None
        if key:
            control = Control(
                framework_key=framework.key,
                identifier=key,
                title=title or None,
                text="",
                depth=0,
                attributes={"structural": True, "source_file": group.get("source_file")},
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            group_uid = control.uid
            counts["groups"] += 1

        section_uids: Dict[str, str] = {}
        ordinal: Dict[str, int] = {}

        for record in group.get("records", []):  # type: ignore[union-attr]
            section_number = str(record.get("section_number", "")).strip()
            section_title = str(record.get("section_title", "")).strip()
            text = str(record.get("text", "")).strip()
            if not text:
                continue

            section_key = "%s §%s" % (key, section_number) if key else section_number
            if section_number and section_key not in section_uids:
                control = Control(
                    framework_key=framework.key,
                    identifier=section_key,
                    title=section_title or None,
                    text="",
                    depth=1,
                    parent_uid=group_uid,
                    section_ref=title or None,
                    attributes={"structural": True},
                    obligation=ObligationStrength.INFORMATIVE,
                    origin=Origin.GENERATED,
                )
                corpus.add_control(control)
                section_uids[section_key] = control.uid
                counts["sections"] += 1

            ordinal[section_key] = ordinal.get(section_key, 0) + 1
            keyword = str(record.get("obligation", "")).strip().upper()
            obligation = OBLIGATION_BY_KEYWORD.get(keyword, ObligationStrength.UNKNOWN)
            obligations[keyword or "none"] = obligations.get(keyword or "none", 0) + 1

            params = record.get("parameters") or []
            if isinstance(params, str):
                params = [params]
            for name in params:
                parameters[str(name)] = parameters.get(str(name), 0) + 1

            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    # '#1' and not '(1)'. Parentheses fold to dots in the identifier
                    # key, so statement §3.2(1) and section §3.2.1 would become the
                    # same control and one would silently replace the other.
                    identifier="%s#%d" % (section_key, ordinal[section_key]),
                    title=None,
                    text=text,
                    depth=2,
                    parent_uid=section_uids.get(section_key),
                    section_ref="%s §%s %s" % (key, section_number, section_title)
                    if section_number
                    else title,
                    publisher_tags={"rfc2119_keyword": keyword} if keyword else {},
                    attributes={"parameters": list(params)},
                    obligation=obligation,
                    obligation_provenance=Provenance.PUBLISHED,
                    origin=Origin.GENERATED,
                )
            )
            counts["statements"] += 1

    counts["parameters"] = parameters
    counts["obligations"] = obligations

    if not counts["statements"]:
        corpus.load_warnings.append(
            "%s: extract contained no statements; the framework stays an empty column "
            "with a stated gap rather than disappearing" % framework.key
        )
    return counts


def load_json(
    corpus: Corpus, framework: Framework, path: str, container: str, group_label: str
) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("revision"):
        framework.revision = str(data["revision"])
        framework.revision_source = str(data.get("revision_source", "the source document"))
    return load_groups(corpus, framework, data.get(container, []), group_label)
