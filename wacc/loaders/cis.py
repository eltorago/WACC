"""CIS Controls v8 and CIS's own mapping to the ASD Essential Eight.

Import only. No CIS text ships.

One trap dominates this file. Safeguard identifiers are stored as numbers, so 3.10
arrives as the float 3.1 and collides with safeguard 3.1 — two different safeguards,
one value. The workbook cannot distinguish them and neither can any reader that trusts
the cell. The catalogue rebuilds identifiers from position: the nth safeguard under
control C is C.n. The mapping workbook can repeat safeguards, so it resolves numeric
values against that catalogue and uses titles to distinguish collisions.
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
)

_NBSP = "\xa0"


def _clean(value: str) -> str:
    return (value or "").replace(_NBSP, " ").strip()


def _control_number(value: str) -> Optional[str]:
    v = _clean(value)
    if not v:
        return None
    try:
        return str(int(float(v)))
    except ValueError:
        return v


def _stored_safeguard(value: str) -> Optional[str]:
    """The cell's own idea of the safeguard number, rounded back from float noise."""
    v = _clean(value)
    if not v:
        return None
    try:
        f = float(v)
    except ValueError:
        return v
    text = ("%.10f" % f).rstrip("0").rstrip(".")
    return text


def load_controls(corpus: Corpus, framework: Framework, path: str) -> Dict[str, int]:
    wb = Workbook(path)
    framework.revision = "v8"
    framework.revision_source = "workbook sheet named 'Controls V8'; the file states no version elsewhere"
    header, body = wb.table("Controls V8")
    idx = {name: i for i, name in enumerate(header)}
    for column in ("CIS Control", "CIS Safeguard", "Title", "Description"):
        if column not in idx:
            raise ValueError("CIS Controls workbook is missing column %r" % column)

    counts = {"controls": 0, "safeguards": 0, "renumbered": 0}
    control_uids: Dict[str, str] = {}
    ordinal: Dict[str, int] = {}

    for row in body:
        number = _control_number(row[idx["CIS Control"]])
        safeguard_cell = row[idx["CIS Safeguard"]]
        title = _clean(row[idx["Title"]])
        description = _clean(row[idx["Description"]])
        if not number:
            continue

        if not _clean(safeguard_cell):
            control = Control(
                framework_key=framework.key,
                identifier=number,
                title=title or None,
                text=description,
                depth=0,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            control_uids[number] = control.uid
            counts["controls"] += 1
            continue

        ordinal[number] = ordinal.get(number, 0) + 1
        identifier = "%s.%d" % (number, ordinal[number])
        stored = _stored_safeguard(safeguard_cell)
        if stored and stored != identifier:
            counts["renumbered"] += 1

        tags: Dict[str, object] = {}
        groups = [g for g in ("IG1", "IG2", "IG3") if idx.get(g) is not None and _clean(row[idx[g]])]
        if groups:
            tags["implementation_groups"] = groups
        for column, key in (("Asset Type", "asset_type"), ("Security Function", "security_function")):
            if column in idx:
                value = _clean(row[idx[column]])
                if value:
                    tags[key] = value

        corpus.add_control(
            Control(
                framework_key=framework.key,
                identifier=identifier,
                title=title or None,
                text=description,
                depth=1,
                parent_uid=control_uids.get(number),
                section_ref="CIS Control %s" % number,
                publisher_tags=tags,
                attributes={"stored_safeguard_value": stored},
                origin=Origin.GENERATED,
            )
        )
        counts["safeguards"] += 1

    if counts["renumbered"]:
        corpus.load_warnings.append(
            "cis-controls: %d safeguard identifiers were rebuilt from position "
            "because the workbook stores them as numbers and cannot tell 3.10 from "
            "3.1" % counts["renumbered"]
        )
    return counts


# --------------------------------------------------------------------------
# CIS Controls to Essential Eight
# --------------------------------------------------------------------------


def load_essential_eight_mapping(
    corpus: Corpus, framework: Framework, path: str
) -> Dict[str, object]:
    """CIS's published mapping from safeguards to Essential Eight strategies.

    The relationship kind — subset or superset — is CIS's own qualifier and is kept.
    Flattening it to 'related' would claim an equivalence CIS did not assert.
    """
    wb = Workbook(path)
    header, body = wb.table("All CIS Controls & Safeguards")
    idx = {name: i for i, name in enumerate(header)}
    for column in ("CIS Control", "CIS Safeguard", "Title", "Relationship"):
        if column not in idx:
            raise ValueError("CIS mapping workbook is missing column %r" % column)
    strategy_col = _security_control_column(header, idx["Relationship"])

    result: Dict[str, object] = {
        "mapped_safeguards": 0,
        "unmapped_safeguards": 0,
        "relationships": {},
        "strategies": {},
    }
    # Numeric workbook cells collapse 3.1 and 3.10. Resolve against catalogue IDs,
    # using titles to distinguish collisions; repeated mapping rows keep their ID.
    candidates: Dict[str, List[Control]] = {}
    for control in corpus.controls_for(framework.key):
        if control.depth == 1:
            candidates.setdefault(_stored_safeguard(control.identifier), []).append(control)
    relationships: Dict[str, int] = {}
    strategies: Dict[str, int] = {}

    for row in body:
        number = _control_number(row[idx["CIS Control"]])
        if not number or not _clean(row[idx["CIS Safeguard"]]):
            continue
        identifier = _stored_safeguard(row[idx["CIS Safeguard"]])
        relationship = _clean(row[idx["Relationship"]])
        strategy = _clean(row[strategy_col]) if strategy_col is not None else ""

        if not relationship or not strategy:
            result["unmapped_safeguards"] += 1
            continue

        matches = candidates.get(identifier, [])
        if len(matches) > 1:
            title = " ".join(_clean(row[idx["Title"]]).casefold().split())
            matches = [c for c in matches if " ".join((c.title or "").casefold().split()) == title]
        if len(matches) != 1:
            corpus.load_warnings.append(
                "cis mapping safeguard %s (%s) cannot be resolved uniquely in the v8 catalogue; "
                "review the v8.1 mapping edition" % (identifier, _clean(row[idx["Title"]]))
            )
            continue
        control = matches[0]

        entries = control.publisher_tags.setdefault("essential_eight", [])
        if isinstance(entries, list):
            entry = {"strategy": strategy, "relationship": relationship}
            if entry not in entries:
                entries.append(entry)
        relationships[relationship] = relationships.get(relationship, 0) + 1
        strategies[strategy] = strategies.get(strategy, 0) + 1
        result["mapped_safeguards"] += 1

    result["relationships"] = relationships
    result["strategies"] = strategies
    return result


def _security_control_column(header: List[str], relationship_col: int) -> Optional[int]:
    """The Essential Eight strategy sits in the column after Relationship.

    It is titled 'Security Control', and the workbook repeats 'Description' twice, so
    matching by name alone picks the wrong one.
    """
    for i in range(relationship_col + 1, len(header)):
        if header[i].strip().lower() == "security control":
            return i
    return relationship_col + 1 if relationship_col + 1 < len(header) else None


# ASD does not publish a mapping from an Essential Eight strategy to the ISM controls
# that implement it. It publishes two things: which controls sit in each maturity
# level, and the ISM's own section headings. Where a heading is word-for-word the
# strategy CIS names, matching them is reading two publishers' labels. Everywhere else
# the connection is this tool's reading of the subject, and these aliases are where
# that reading is written down so it can be argued with.
# A section is not always the right granularity, and taking whole sections put sixteen of
# thirty-five patch links on the wrong strategy. 'Mitigating known vulnerabilities' holds
# both the application patching controls and the operating system ones, and the ISM
# distinguishes them in the control text rather than in the heading: ISM-1692 is about
# office productivity suites and ISM-1694 about operating systems, in the same section.
# 'Cessation of support' does the same, and 'Office productivity suites' holds the macro
# settings beside Office hardening that belongs to a different strategy altogether.
#
# So an alias may narrow a section by what the control itself says. `requires` keeps only
# controls whose text carries one of the phrases; `excludes` drops those that do. Both are
# this tool's reading, written where it can be argued with, and every link this route makes
# is derived for that reason.
STRATEGY_SECTION_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "patch applications": {
        "sections": ["mitigating known vulnerabilities", "cessation of support"],
        "excludes": ["operating system"],
    },
    "patch os systems": {
        "sections": [
            "operating system releases and versions",
            "mitigating known vulnerabilities",
            "cessation of support",
        ],
        "requires": ["operating system"],
    },
    "configure ms office macros": {
        "sections": ["office productivity suites"],
        # Office hardening — OLE, child processes, code injection, trusted publishers —
        # sits in the same section and is User Application Hardening, a different strategy.
        "requires": ["macro"],
    },
    "restricting administrative privileges": {
        "sections": [
            "privileged access to systems",
            "separate privileged operating environments",
            "administrative infrastructure",
        ],
        # Not narrowed: jump servers, just-in-time administration and Secure Admin
        # Workstations never say "privileged" and are squarely this strategy.
    },
    "daily backups": {"sections": ["data backup and restoration"]},
}


def _alias_allows(text: str, alias: Dict[str, List[str]]) -> bool:
    """Whether a control's own words put it inside this reading of the strategy."""
    lowered = (text or "").lower()
    requires = alias.get("requires") or []
    if requires and not any(phrase in lowered for phrase in requires):
        return False
    return not any(phrase in lowered for phrase in (alias.get("excludes") or []))


def link_safeguards_to_ism(
    corpus: Corpus, cis_key: str = "cis-controls", ism_key: str = "ism"
) -> Dict[str, object]:
    """Join Essential Eight strategy names to ISM controls, by two routes.

    Where the ISM section heading is the strategy name, both ends carry a publisher's
    own label and the link is published-tag, with the join named as this tool's.

    Where it is not, an alias above says what this tool thinks the strategy covers.
    That is a subject judgement, so the link is derived and no lineage view will show
    it. Calling that route published would be the most flattering error available
    here, and the least defensible in a finding.
    """
    sections: Dict[str, List[str]] = {}
    for uid, control in corpus.controls.items():
        if control.framework_key != ism_key:
            continue
        if not control.tag_list("essential_eight_maturity"):
            continue
        for segment in (control.section_ref or "").split(">"):
            key = segment.strip().lower()
            if key:
                sections.setdefault(key, []).append(uid)

    counts = {
        "published_tag_links": 0,
        "derived_links": 0,
        "strategies_by_route": {},
        "strategies_unmatched": [],
    }
    routes: Dict[str, str] = {}
    unmatched: List[str] = []

    for uid, control in corpus.controls.items():
        if control.framework_key != cis_key:
            continue
        entries = control.publisher_tags.get("essential_eight")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            named = str(entry.get("strategy", "")).strip()
            strategy = named.lower()
            relationship = entry.get("relationship")

            targets = sections.get(strategy)
            if targets:
                routes[named] = "published-tag"
                for target in targets:
                    corpus.add_link(
                        Link(
                            source_uid=uid,
                            target_uid=target,
                            provenance=Provenance.PUBLISHED_TAG,
                            basis=(
                                "CIS maps this safeguard to Essential Eight strategy "
                                "%r (%s); the ISM heading of the same name holds these "
                                "controls" % (named, relationship)
                            ),
                            tag_side=(
                                "both ends published; matching the CIS strategy name "
                                "to the ISM heading is this tool's"
                            ),
                        )
                    )
                    counts["published_tag_links"] += 1
                continue

            alias = STRATEGY_SECTION_ALIASES.get(strategy)
            if not alias:
                unmatched.append(named)
                continue
            routes[named] = "derived"
            narrowed = ", ".join(alias.get("requires") or alias.get("excludes") or [])
            for section in alias["sections"]:
                for target in sections.get(section, []):
                    if not _alias_allows(corpus.controls[target].text, alias):
                        continue
                    corpus.add_link(
                        Link(
                            source_uid=uid,
                            target_uid=target,
                            provenance=Provenance.DERIVED,
                            basis=(
                                "CIS maps this safeguard to Essential Eight strategy "
                                "%r (%s); this tool reads that strategy as covering the "
                                "ISM section %r%s"
                                % (
                                    named, relationship, section,
                                    (", narrowed to controls whose text %s %r"
                                     % ("carries" if alias.get("requires") else "omits",
                                        narrowed)) if narrowed else "",
                                )
                            ),
                        )
                    )
                    counts["derived_links"] += 1

    counts["strategies_by_route"] = routes
    if unmatched:
        distinct = sorted(set(unmatched))
        counts["strategies_unmatched"] = distinct
        corpus.load_warnings.append(
            "cis-to-ism: %d Essential Eight strategy names reach no ISM controls by "
            "either route: %s" % (len(distinct), "; ".join(distinct))
        )
    return counts
