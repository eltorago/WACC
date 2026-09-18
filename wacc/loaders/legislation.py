"""Commonwealth legislation from Federal Register of Legislation Word files.

A docx is a zip of XML, so this runs anywhere the tool runs. No extraction detour.

Structure comes from paragraph styles, not from text that happens to start with a
number. ActHead 2/3 are Parts and Divisions, ActHead 5 is a section, and the obligation
itself almost always sits in a subsection. Table of contents and endnote styles are
skipped, because both repeat every heading in the document and would double the corpus.

Tables are provisions here, not decoration. CIRMP Rules s 8(4) discharges the cyber and
information security obligation by naming documents in a table, and each row is the
Commonwealth asserting a link from statute to a framework. Those are the strongest
links this tool can carry.
"""

import re
from typing import Dict, List, Optional, Tuple

from ..io.docx import Document, Paragraph, Table
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

SKIP_STYLE_PREFIXES = ("toc", "ENote", "header", "footer", "Header", "Footer")

_HEAD_ID = re.compile(r"^((?:Part|Division|Schedule)?\s*[0-9]+[A-Z]*)\s*[—-]?\s*(.*)$")
_SECTION_ID = re.compile(r"^([0-9]+[A-Z]*)\s+(.*)$")
_SUBSECTION_ID = re.compile(r"^\(([0-9]+[A-Za-z]*)\)\s*(.*)$")
_PARA_ID = re.compile(r"^\(([a-z]+)\)\s*(.*)$")

# Obligation strength stated by the drafting, not inferred from tone. 'Must' and 'must
# not' are the operative forms in Commonwealth drafting; 'may' confers a power.
_MUST_NOT = re.compile(r"\bmust not\b|\bmay not\b", re.IGNORECASE)
_MUST = re.compile(r"\bmust\b|\bis required to\b|\bshall\b", re.IGNORECASE)
_MAY = re.compile(r"\bmay\b", re.IGNORECASE)


# Documents a framework-naming table can point at, and what this tool holds for each.
# Declared rather than fuzzy-matched: a wrong match here would put a framework inside a
# legal obligation it is not named in.
NAMED_DOCUMENTS: List[Tuple[str, Optional[str], str]] = [
    ("The NIST Cybersecurity Framework (CSF) 2.0", "csf", "loaded"),
    (
        "Framework for Improving Critical Infrastructure Cybersecurity",
        None,
        "not loaded — this is NIST CSF 1.1 under its former title; the corpus holds "
        "CSF 2.0, which the Rules name separately in s 8A",
    ),
    # Two editions, two rows, two different documents. s 8(4) names the 2020-21 core and
    # s 8A(3) names the 2023 core, and one entry matching the phrase they share put the
    # one workbook the corpus holds inside both obligations. The corpus holds Framework
    # Core V2, which Aidan confirmed is the 2023 edition; the workbook states no edition
    # of its own anywhere in its cells.
    ("202021 AESCSF Framework Core", None,
     "not loaded — this names the 2020-21 edition. The corpus holds the 2023 Framework "
     "Core, which is the edition s 8A(3) names"),
    ("2023 AESCSF Framework Core", "aescsf", "loaded"),
    (
        "Essential Eight Maturity Model",
        None,
        "not linked — WACC can import the November 2023 model, but the edition and "
        "maturity level required by this provision need a separate incorporation review",
    ),
    (
        "AS ISO/IEC 27001",
        None,
        "not loaded — ISO text cannot be redistributed and no importer exists yet",
    ),
    # Both rows resolve to the one document. s 8(4) names C2M2 with no version, and
    # s 8(4)(a) reads the table "as in force from time to time", so it points at whatever
    # edition is current; s 8A(3) pins Version 2.1 by name. Version 2.1 of June 2022 is
    # what the DOE publishes as current, so both rows land on the same corpus framework
    # and differ only in the level they require.
    ("Cybersecurity Capability Maturity Model", "c2m2", "loaded"),
]


def _skip(style: str) -> bool:
    return any(style.startswith(prefix) for prefix in SKIP_STYLE_PREFIXES)


def obligation_of(text: str) -> ObligationStrength:
    if _MUST_NOT.search(text):
        return ObligationStrength.PROHIBITED
    if _MUST.search(text):
        return ObligationStrength.MANDATORY
    if _MAY.search(text):
        return ObligationStrength.PERMITTED
    return ObligationStrength.INFORMATIVE


def is_framework_table(table: Table) -> bool:
    if not table.rows:
        return False
    header = " ".join(c.lower() for c in table.rows[0])
    return "document" in header and "condition" in header


def resolve_document(cell: str) -> Tuple[Optional[str], str, str]:
    """Return (framework key or None, matched phrase, note)."""
    for phrase, key, note in NAMED_DOCUMENTS:
        if phrase.lower() in cell.lower():
            return key, phrase, note
    return None, "", "not recognised — no entry in NAMED_DOCUMENTS matches this row"


def load_into(corpus: Corpus, framework: Framework, path: str) -> Dict[str, object]:
    doc = Document(path)
    counts = {
        "parts": 0,
        "sections": 0,
        "subsections": 0,
        "framework_tables": 0,
        "named_documents": 0,
        "published_links": 0,
        "unresolved_documents": [],
    }

    part_identifier: Optional[str] = None
    part_uid: Optional[str] = None
    division_uid: Optional[str] = None
    section_number: Optional[str] = None
    section_uid: Optional[str] = None
    section_title: Optional[str] = None
    current_subsection: Optional[Control] = None
    pending_links: List[Tuple[str, str, str]] = []
    unresolved: List[str] = []

    for block in doc.blocks():
        if isinstance(block, Table):
            if current_subsection is None or not is_framework_table(block):
                continue
            counts["framework_tables"] += 1
            named: List[Dict[str, str]] = []
            for row in block.rows[1:]:
                if len(row) < 2 or not row[1].strip():
                    continue
                document = row[1].strip()
                condition = row[2].strip() if len(row) > 2 else ""
                key, phrase, note = resolve_document(document)
                named.append(
                    {
                        "document": document,
                        "condition": condition,
                        "framework": key or "",
                        "status": "loaded" if key else note,
                    }
                )
                counts["named_documents"] += 1
                if key:
                    pending_links.append((current_subsection.uid, key, condition))
                else:
                    unresolved.append(document)
            if named:
                current_subsection.attributes["named_documents"] = named
            continue

        if _skip(block.style) or not block.text:
            continue

        style = block.style

        if style.startswith("ActHead 2") or style.startswith("ActHead 3"):
            match = _HEAD_ID.match(block.text)
            identifier = match.group(1).strip() if match else block.text[:24]
            title = match.group(2).strip() if match else ""
            is_division = style.startswith("ActHead 3")
            if is_division and part_identifier:
                # Divisions are numbered within their Part, so 'Division 1' occurs
                # once per Part. Unqualified, they collide and the second one wins.
                identifier = "%s %s" % (part_identifier, identifier)
            control = Control(
                framework_key=framework.key,
                identifier=identifier,
                title=title or None,
                text="",
                depth=1 if is_division else 0,
                parent_uid=part_uid if is_division else None,
                attributes={"structural": True},
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            if is_division:
                division_uid = control.uid
            else:
                part_identifier = identifier
                part_uid = control.uid
                division_uid = None
            counts["parts"] += 1
            section_number = section_uid = None
            current_subsection = None
            continue

        if style.startswith("ActHead 5") or style.startswith("ActHead 6"):
            # An unsupported heading (for example a schedule) ends the prior body.
            section_number = section_uid = None
            current_subsection = None
            match = _SECTION_ID.match(block.text)
            if not match:
                continue
            section_number = match.group(1)
            section_title = match.group(2).strip()
            control = Control(
                framework_key=framework.key,
                identifier="s %s" % section_number,
                title=section_title or None,
                text="",
                depth=2,
                parent_uid=division_uid or part_uid,
                attributes={"structural": True},
                obligation=ObligationStrength.INFORMATIVE,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            section_uid = control.uid
            current_subsection = None
            counts["sections"] += 1
            continue

        if style == "subsection" and section_number:
            match = _SUBSECTION_ID.match(block.text)
            if not match:
                # A section with no numbered subsections states its requirement here.
                current_subsection = corpus.control(section_uid)
                current_subsection.text = (current_subsection.text + "\n" + block.text).strip()
                current_subsection.attributes.pop("structural", None)
                current_subsection.obligation = obligation_of(current_subsection.text)
                current_subsection.obligation_provenance = Provenance.DERIVED
                continue
            number, text = match.group(1), match.group(2).strip()
            control = Control(
                framework_key=framework.key,
                identifier="s %s(%s)" % (section_number, number),
                title=None,
                text=text,
                depth=3,
                parent_uid=section_uid,
                section_ref=section_title,
                obligation=obligation_of(text),
                obligation_provenance=Provenance.DERIVED,
                origin=Origin.GENERATED,
            )
            corpus.add_control(control)
            current_subsection = control
            counts["subsections"] += 1
            continue

        if style in ("subsection2", "paragraph", "paragraph(sub)", "Definition", "Penalty") and current_subsection is not None:
            # Lettered paragraphs continue the obligation their subsection opens, so
            # they extend its text rather than becoming controls of their own. Splitting
            # them would produce fragments that state no obligation on their own.
            current_subsection.text = (current_subsection.text + "\n" + block.text).strip()
            current_subsection.obligation = obligation_of(current_subsection.text)
            continue

        if style.startswith("note") and current_subsection is not None:
            notes = current_subsection.attributes.setdefault("notes", [])
            if isinstance(notes, list):
                notes.append(block.text)

    counts["published_links"] = _attach_named_frameworks(corpus, framework, pending_links)
    counts["unresolved_documents"] = sorted(set(unresolved))
    if unresolved:
        corpus.load_warnings.append(
            "%s: %d framework-table rows lack resolved links to the required document editions: %s"
            % (framework.key, len(unresolved), "; ".join(sorted(set(unresolved))[:6]))
        )
    return counts


def _attach_named_frameworks(
    corpus: Corpus, framework: Framework, pending: List[Tuple[str, str, str]]
) -> int:
    """Link a provision to every control of a framework it names.

    The Commonwealth asserts this in a legislative instrument, so the provenance is
    published and it is the most citable link in the tool. The link points at the
    framework's top-level controls rather than at all of them; naming a framework
    incorporates the framework, not each of its leaves.

    The table's condition column travels with the link. For a maturity framework the
    condition is the obligation: s 8(4) names the AESCSF at Security Profile 1 and
    s 8A(3) names it at Security Profile 2, and a link that records only "named in the
    framework table" shows the two provisions requiring the same thing. They do not.
    """
    attached = 0
    for source_uid, target_key, condition in pending:
        basis = "named in the framework table of this provision"
        if condition:
            basis = "%s — condition: %s" % (basis, condition)
        roots = [
            c.uid
            for c in corpus.controls_for(target_key)
            if c.depth == 0 and not c.attributes.get("structural")
        ]
        if not roots:
            roots = [c.uid for c in corpus.controls_for(target_key) if c.depth == 0]
        if not roots:
            # The document resolved to a framework the corpus knows and that framework
            # has no controls yet, which means it loads after this one. Silent here, it
            # reads in the output as an instrument naming nothing.
            corpus.load_warnings.append(
                "%s names %s in a framework table, but %s has no controls loaded yet — "
                "it must load before tier 1" % (framework.key, target_key, target_key)
            )
            continue
        for target_uid in roots:
            corpus.add_link(
                Link(
                    source_uid=source_uid,
                    target_uid=target_uid,
                    provenance=Provenance.PUBLISHED,
                    basis=basis,
                    kind=LinkKind.INCORPORATES,
                    asserted_by="Commonwealth of Australia",
                )
            )
            attached += 1
    return attached
