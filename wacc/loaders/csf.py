"""NIST CSF 2.0 from NIST's CPRT export, with its OLIR informative references.

Two things in this file are not what they look like.

The export interleaves withdrawn CSF 1.1 elements with live CSF 2.0 ones, marked
'[Withdrawn: ...]'. Loading those as controls would invent obligations that NIST
retired. They load instead as published redirects, so someone citing ID.AM-06 is told
where it went.

Each function block ends with a bare repeat of the function name. That row is a
delimiter, not a second function.
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

_WITHDRAWN = re.compile(r"^\[Withdrawn[:\]]", re.IGNORECASE)
_ID_IN_PARENS = re.compile(r"\(([A-Z]{2}(?:\.[A-Z]{2})?)\)\s*:?\s*")
_SUB_ID = re.compile(r"^([A-Z]{2}\.[A-Z]{2}-\d{2})\s*:\s*(.*)$", re.DOTALL)
# A withdrawal can redirect to a subcategory, a category, or a whole function, so
# 'Incorporated into GV' has to match as readily as 'Moved to GV.RM-04'.
_REDIRECT = re.compile(r"\b([A-Z]{2}(?:\.[A-Z]{2}(?:-\d{2})?)?)\b")

# Reference source labels that name a framework this tool loads. The revision is part
# of the key on purpose: a mapping to 800-53 Rev 5.1.1 is not a mapping to the 5.2.0
# catalog that is actually loaded, and pretending otherwise would cite the wrong text.
REFERENCE_SOURCES: Dict[str, str] = {
    "SP 800-53 Rev 5.2.0": "nist-800-53",
    "CIS Controls v8.0": "cis-controls",
}


def _split_id_and_text(cell: str) -> Tuple[Optional[str], str]:
    text = (cell or "").strip()
    m = _SUB_ID.match(text)
    if m:
        return m.group(1), m.group(2).strip()
    m2 = _ID_IN_PARENS.search(text)
    if m2:
        ident = m2.group(1)
        rest = text[m2.end() :].strip()
        return ident, rest
    return None, text


def parse_references(cell: str) -> List[Tuple[str, str]]:
    """Return (source label, identifier) for each reference line."""
    out: List[Tuple[str, str]] = []
    for line in (cell or "").split("\n"):
        line = line.strip().rstrip(",")
        if not line or ":" not in line:
            continue
        source, ident = line.split(":", 1)
        ident = ident.strip()
        if ident:
            out.append((source.strip(), ident))
    return out


def load_into(corpus: Corpus, framework: Framework, path: str, sheet: str = "CSF 2.0") -> Dict[str, int]:
    wb = Workbook(path)
    rows = list(wb.rows(sheet))
    _set_revision(framework, rows)
    counts = {
        "functions": 0,
        "categories": 0,
        "subcategories": 0,
        "withdrawn": 0,
        "redirects": 0,
        "references_published": 0,
        "references_external": 0,
    }

    seen_functions = set()
    current_function: Optional[str] = None
    current_category: Optional[str] = None
    pending_refs: List[Tuple[str, str, str]] = []  # (control uid, source, identifier)

    for row in rows[2:]:
        row = list(row) + [""] * (5 - len(row))
        col0, col1, col2, examples, refs = row[0], row[1], row[2], row[3], row[4]

        if col0.strip():
            ident, text = _split_id_and_text(col0)
            if not text:
                # Bare function name closing a block, not a second function.
                continue
            if ident and ident in seen_functions:
                continue
            if ident:
                seen_functions.add(ident)
                current_function = ident
                counts["functions"] += 1
                corpus.add_control(
                    Control(
                        framework_key=framework.key,
                        identifier=ident,
                        title=col0.split("(")[0].strip() or None,
                        text=text,
                        depth=0,
                        origin=Origin.GENERATED,
                    )
                )
            continue

        if col1.strip():
            ident, text = _split_id_and_text(col1)
            if not ident:
                continue
            current_category = ident
            if _WITHDRAWN.match(text):
                counts["withdrawn"] += 1
                counts["redirects"] += _record_redirects(corpus, framework, ident, text)
                continue
            counts["categories"] += 1
            parent = "%s:%s" % (framework.key, current_function.lower()) if current_function else None
            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    identifier=ident,
                    title=col1.split("(")[0].strip() or None,
                    text=text,
                    depth=1,
                    parent_uid=parent,
                    section_ref=current_function,
                    origin=Origin.GENERATED,
                )
            )
            continue

        if col2.strip():
            ident, text = _split_id_and_text(col2)
            if not ident:
                continue
            if _WITHDRAWN.match(text):
                counts["withdrawn"] += 1
                counts["redirects"] += _record_redirects(corpus, framework, ident, text)
                continue
            counts["subcategories"] += 1
            parent = (
                "%s:%s" % (framework.key, current_category.lower())
                if current_category
                else None
            )
            attributes: Dict[str, object] = {}
            if examples.strip():
                attributes["implementation_examples"] = examples.strip()
            external: List[str] = []
            control = Control(
                framework_key=framework.key,
                identifier=ident,
                title=None,
                text=text,
                depth=2,
                parent_uid=parent,
                section_ref="%s > %s" % (current_function, current_category)
                if current_function and current_category
                else None,
                attributes=attributes,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            for source, target in parse_references(refs):
                if source in REFERENCE_SOURCES:
                    pending_refs.append((control.uid, source, target))
                else:
                    external.append("%s: %s" % (source, target))
            if external:
                attributes["external_references"] = external
                counts["references_external"] += len(external)

    counts["references_published"] = _attach_references(corpus, pending_refs)
    return counts


_VERSION = re.compile(r"Cybersecurity Framework\s+([0-9]+\.[0-9]+)")


def _set_revision(framework: Framework, rows: List[List[str]]) -> None:
    """Take the version from the export's own title cell rather than the filename."""
    for row in rows[:2]:
        for cell in row:
            m = _VERSION.search(cell or "")
            if m:
                framework.revision = m.group(1)
                framework.revision_source = "title cell of the CPRT export"
                return


def _record_redirects(
    corpus: Corpus, framework: Framework, ident: str, text: str
) -> int:
    """A withdrawn element becomes a signpost, not a control.

    NIST states where the outcome went. That statement is published, so someone who
    cites a retired CSF 1.1 subcategory can be pointed at the live one rather than
    told nothing was found.
    """
    targets = [t for t in _REDIRECT.findall(text) if t != ident]
    framework.withdrawn_redirects[ident] = targets

    if not targets:
        corpus.load_warnings.append(
            "csf: %s is marked withdrawn but names no replacement" % ident
        )
    return len(targets)


def _attach_references(corpus: Corpus, pending: List[Tuple[str, str, str]]) -> int:
    """Published links, one per informative reference NIST states.

    NIST asserts these, so the provenance is published and the lineage view may show
    them. Anything whose target framework is not loaded stays an attribute on the
    control instead of becoming a link to nowhere.
    """
    from ..model import normalise_identifier

    attached = 0
    index: Dict[Tuple[str, str], str] = {}
    for uid, control in corpus.controls.items():
        index[(control.framework_key, control.identifier_key)] = uid

    for source_uid, source_label, target_identifier in pending:
        framework_key = REFERENCE_SOURCES[source_label]
        target_uid = index.get((framework_key, normalise_identifier(target_identifier)))
        if target_uid is None:
            continue
        corpus.add_link(
            Link(
                source_uid=source_uid,
                target_uid=target_uid,
                provenance=Provenance.PUBLISHED,
                basis="NIST OLIR informative reference (%s)" % source_label,
                asserted_by="NIST",
            )
        )
        attached += 1
    return attached
