"""CIS Controls v8 and CIS's own mapping to the ASD Essential Eight.

Import only. No CIS text ships.

One trap dominates this file. Safeguard identifiers are stored as numbers, so 3.10
arrives as the float 3.1 and collides with safeguard 3.1 — two different safeguards,
one value. The workbook cannot distinguish them and neither can any reader that trusts
the cell. Identifiers are therefore rebuilt from position: the nth safeguard listed
under control C is C.n, and the stored value is used only to confirm it.
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
    for column in ("CIS Control", "CIS Safeguard", "Relationship"):
        if column not in idx:
            raise ValueError("CIS mapping workbook is missing column %r" % column)
    strategy_col = _security_control_column(header, idx["Relationship"])

    result: Dict[str, object] = {
        "mapped_safeguards": 0,
        "unmapped_safeguards": 0,
        "relationships": {},
        "strategies": {},
    }
    ordinal: Dict[str, int] = {}
    relationships: Dict[str, int] = {}
    strategies: Dict[str, int] = {}

    for row in body:
        number = _control_number(row[idx["CIS Control"]])
        if not number or not _clean(row[idx["CIS Safeguard"]]):
            continue
        ordinal[number] = ordinal.get(number, 0) + 1
        identifier = "%s.%d" % (number, ordinal[number])
        relationship = _clean(row[idx["Relationship"]])
        strategy = _clean(row[strategy_col]) if strategy_col is not None else ""

        if not relationship or not strategy:
            result["unmapped_safeguards"] += 1
            continue

        uid = "%s:%s" % (framework.key, identifier)
        control = corpus.control(uid)
        if control is None:
            corpus.load_warnings.append(
                "cis mapping names safeguard %s, which the v8 catalogue does not "
                "contain; the mapping workbook is v8.1" % identifier
            )
            continue

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
STRATEGY_SECTION_ALIASES: Dict[str, List[str]] = {
    "patch applications": ["mitigating known vulnerabilities", "cessation of support"],
    "patch os systems": [
        "operating system releases and versions",
        "mitigating known vulnerabilities",
    ],
    "configure ms office macros": ["office productivity suites"],
    "restricting administrative privileges": [
        "privileged access to systems",
        "separate privileged operating environments",
        "administrative infrastructure",
    ],
    "daily backups": ["data backup and restoration"],
}


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

            aliases = STRATEGY_SECTION_ALIASES.get(strategy)
            if not aliases:
                unmatched.append(named)
                continue
            routes[named] = "derived"
            for alias in aliases:
                for target in sections.get(alias, []):
                    corpus.add_link(
                        Link(
                            source_uid=uid,
                            target_uid=target,
                            provenance=Provenance.DERIVED,
                            basis=(
                                "CIS maps this safeguard to Essential Eight strategy "
                                "%r (%s); this tool reads that strategy as covering "
                                "the ISM section %r" % (named, relationship, alias)
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
