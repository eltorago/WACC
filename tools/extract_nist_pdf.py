"""Extract parameter statements from the tier-5 NIST PDFs.

Extraction tooling. Not part of the shipped package.

Two routes, because these documents keep their parameters in two places.

Sentences. A sentence is kept when it is normative *and* states a parameter — a count,
period, length, algorithm, date or level. The same rule runs over every tier-5 document
on purpose: a threshold comparison between corpora extracted by different judgements
would compare the judgements rather than the documents.

Tables. The sentence route came back nearly empty on most of these, because the numbers
are tabulated rather than written out. SP 800-88 Rev 2 contains one 'shall' in 48 pages
while its Appendix A is a full media-type sanitization matrix, and SP 800-57's
cryptoperiods are a table too. A table row is kept when the table it belongs to is
mostly parameters, which is what separates a cryptoperiod table from a glossary.

Sections whose title marks them as front or back matter are skipped in both routes.
Without that, an acronym list parses into sentences that read like requirements.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textjoin import mend_hyphen  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTS = os.path.join(HERE, "data", "raw", "documents")
CORPUS = os.path.join(HERE, "data", "corpus")
# The sentence route is a report, not a corpus. Its output lands here and is loaded by
# nothing, because these PDFs do not preserve word order reliably and a garbled sentence
# quoted in a finding is worse than a stated gap.
REVIEW = os.path.join(HERE, "data", "review")

DOCS = [
    {
        "key": "nist-800-131a",
        "file": "NIST.SP.800-131Ar2.pdf",
        "group": "SP 800-131A Rev 2",
        "title": "Transitioning the Use of Cryptographic Algorithms and Key Lengths",
    },
    {
        "key": "nist-800-57pt1",
        "file": "nist.sp.800-57pt1r5.pdf",
        "group": "SP 800-57 Part 1 Rev 5",
        "title": "Recommendation for Key Management: General",
    },
    {
        "key": "nist-800-88",
        "file": "NIST.SP.800-88r2.pdf",
        "group": "SP 800-88 Rev 2",
        "title": "Guidelines for Media Sanitization",
    },
    {
        "key": "fips-140-3",
        "file": "NIST.FIPS.140-3.pdf",
        "group": "FIPS 140-3",
        "title": "Security Requirements for Cryptographic Modules",
    },
    {
        "key": "nist-800-92",
        "file": "nist-sp-800-92.pdf",
        "group": "SP 800-92",
        "title": "Guide to Computer Security Log Management",
    },
    {
        "key": "nist-800-34",
        "file": "nistspecialpublication800-34r1.pdf",
        "group": "SP 800-34 Rev 1",
        "title": "Contingency Planning Guide for Federal Information Systems",
    },
]

# The first component is one or two digits. Without that bound, a table cell reading
# "2030 Applying protection" is read as section 2030 and every statement under it is
# cited to a section that does not exist.
_HEADING = re.compile(r"^(\d{1,2}(?:\.\d+){0,3})\.?\s+([A-Z][^.]{2,80})$")
_APPENDIX = re.compile(r"^appendix\s+([a-z])\b[\s—:.-]*(.*)$", re.IGNORECASE)
_LEADER = re.compile(r"[·•….]{4,}")
# A caption, not a prose reference. "Table 1: Suggested cryptoperiods" is a caption;
# "Table 1 below is a summary of the cryptoperiods that are suggested for..." is a
# sentence, and pairing that with the table underneath it labels the data wrongly.
_TABLE_CAPTION = re.compile(r"^table\s+(\d+)\s*[:.]\s+(\S.*)$", re.IGNORECASE)
# A caption does not always start the line it sits on. On page 67 of SP 800-57 a full
# stop from the paragraph above shares the caption's baseline, so the line reads
# ". Table 2: Comparable security strengths of..." and an anchored match lost Table 2
# and every row under it. Leading non-letters are dropped before the match; a prose
# reference still cannot match, because it has no colon after the number.
_CAPTION_LEAD = re.compile(r"^[^A-Za-z]*(?=table\b)", re.IGNORECASE)
# How far below a caption a wrapped second line can sit, and how much of one it can be.
CAPTION_WRAP_GAP = 22.0
CAPTION_WRAP_CHARS = 60
_NORMATIVE = re.compile(r"\b(shall not|should not|must not|shall|should|must)\b", re.IGNORECASE)

# Front and back matter. Sentences here read like requirements and are not.
_NOT_GUIDANCE = re.compile(
    r"^(acronyms?|abbreviations?|glossary|references?|bibliograph|change log|"
    r"revision history|document conventions|list of (?:symbols|tables|figures)|"
    r"executive summary|table of contents|notations?|purpose|audience|"
    r"acknowledge?ments?|foreword|abstract|keywords)\b",
    re.IGNORECASE,
)

_PARAMETER_PATTERNS: List[Tuple[str, str]] = [
    ("period", r"\b\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b"),
    ("length", r"\b\d+\s*(?:bits?|bytes?|characters?|digits?|octets?)\b"),
    ("bound", r"\b(?:at least|no more than|no fewer than|not exceed|a minimum of|a maximum of|greater than|less than)\s+\d"),
    ("date", r"\b(?:through|after|until|by|beyond)\s+(?:December\s+31,\s*)?20\d\d\b"),
    ("algorithm", r"\b(?:SHA-?\d+|SHA-?3|AES(?:-\d+)?|RSA|ECDSA|EdDSA|HMAC|PBKDF2|Triple\s*DES|TDEA|DSA|Diffie-Hellman|TLS\s*1\.\d|FIPS\s*140(?:-\d)?)\b"),
    ("strength", r"\b\d+\s*bits? of (?:security|strength|entropy)\b"),
    ("level", r"\bsecurity level\s*[1-4]\b"),
    ("method", r"\b(?:Clear|Purge|Destroy|Cryptographic Erase)\b"),
]

_ABBREV = r"(?<!\bSec)(?<!\be\.g)(?<!\bi\.e)(?<!\bU\.S)(?<!\bFig)(?<!\bNo)(?<!\bvs)"
_SENTENCE = re.compile(_ABBREV + r"(?<=[.!?])\s+(?=[A-Z(])")

TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}

# Only these tables enter the corpus. Selecting by caption is curation written down:
# someone can check the list against the document's own list of tables, which is not
# true of a heuristic that decides table by table.
WANTED_TABLES: Dict[str, List[str]] = {
    "nist-800-57pt1": [
        "suggested cryptoperiods",
        "comparable security strengths",
        "maximum security strengths",
        "security strength time frames",
    ],
    "nist-800-131a": ["approval status"],
}


class Line:
    def __init__(self, words: List[dict]) -> None:
        self.text = " ".join(w["text"] for w in words).strip()
        self.x0 = min(w["x0"] for w in words)
        self.top = min(w["top"] for w in words)
        self.size = max(w["size"] for w in words)
        bold = sum(len(w["text"]) for w in words if "Bold" in w["fontname"])
        total = sum(len(w["text"]) for w in words) or 1
        self.bold = bold / total > 0.5


def page_lines(page) -> List[Line]:
    buckets: Dict[int, List[dict]] = {}
    for word in page.extract_words(extra_attrs=["fontname", "size"]):
        buckets.setdefault(round(word["top"]), []).append(word)
    return [Line(sorted(buckets[top], key=lambda w: w["x0"])) for top in sorted(buckets)]


def page_captions(lines: List["Line"]) -> List[str]:
    """Table captions on one page, in reading order, wrapped lines joined.

    Two things this has to survive, both real on SP 800-57 page 67. A caption need not
    start its own line: a full stop from the paragraph above sits on the same baseline.
    And a caption wider than the text column wraps, so 'asymmetric-key' and 'algorithms'
    land on separate lines — a caption stored without its last word is a misquote, and
    the caption is the first half of every row's text.
    """
    out: List[str] = []
    for i, line in enumerate(lines):
        text = _CAPTION_LEAD.sub("", line.text.strip())
        if len(text) > 110 or not _TABLE_CAPTION.match(text):
            continue
        if not text.endswith("."):
            # Not simply the next line. A footnote digit at five points sits between the
            # caption and its second line on SP 800-57 page 67, so the search skips past
            # anything set differently and stops at the first line in the same face.
            for following in lines[i + 1 : i + 5]:
                gap = following.top - line.top
                if gap <= 0 or gap > CAPTION_WRAP_GAP:
                    continue
                if abs(following.size - line.size) >= 0.6 or following.bold != line.bold:
                    continue
                tail = following.text.strip()
                if tail[:1].islower() and len(tail) < CAPTION_WRAP_CHARS:
                    text = "%s %s" % (text, tail)
                break
        out.append(text)
    return out


def parameters_in(text: str) -> List[str]:
    found = []
    for name, pattern in _PARAMETER_PATTERNS:
        flags = 0 if name in ("algorithm", "method") else re.IGNORECASE
        if re.search(pattern, text, flags):
            found.append(name)
    return found


def _body_size(pdf) -> float:
    counts: Dict[float, int] = {}
    for page in pdf.pages[: min(20, len(pdf.pages))]:
        for word in page.extract_words(extra_attrs=["fontname", "size"]):
            size = round(word["size"], 1)
            counts[size] = counts.get(size, 0) + len(word["text"])
    return max(counts, key=lambda s: counts[s]) if counts else 11.0


# A footnote marker is a superscript in the PDF and plain digits in the extracted text,
# so SP 800-57 Table 1 rendered "< 2 years61", "1 to 2 years62" and "1 to 2 years63" —
# footnotes 61 to 63 welded onto the unit. The threshold reader saw no quantity at all in
# any of them, so three of the document's stated cryptoperiods were invisible to every
# comparison. Only a time unit is unwelded: no figure is written "2 years61", while
# AES-128 and SHA3-256 are names with digits in them and are left alone.
_WELDED_FOOTNOTE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:second|minute|hour|day|week|month|year)s?)\d{1,3}\b",
    re.IGNORECASE,
)


def _clean(cell: Optional[str]) -> str:
    text = re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()
    return mend_hyphen(_WELDED_FOOTNOTE.sub(r"\1", text))


# --------------------------------------------------------------------------
# Route 1 — normative sentences
# --------------------------------------------------------------------------


def walk_sections(pdf, body_size: float) -> List[Dict[str, object]]:
    """Split the document into sections, carrying each table with the section it sits in."""
    sections: List[Dict[str, object]] = []
    current: Dict[str, object] = {"number": "", "title": "(front matter)", "body": [], "tables": []}
    walk_sections.uncaptioned = 0
    walk_sections.last_caption = ""
    walk_sections.last_caption_page = -99

    for number, page in enumerate(pdf.pages):
        page_tables = page.extract_tables(TABLE_SETTINGS)
        lines = page_lines(page)
        captions = page_captions(lines)
        for line in lines:
            text = line.text.strip()
            if not text or _LEADER.search(text):
                continue
            if line.size < body_size - 1.5:
                continue
            heading = _HEADING.match(text)
            appendix = _APPENDIX.match(text) if line.bold else None
            if (heading and (line.bold or line.size > body_size + 0.5) and len(text) < 90) or appendix:
                sections.append(current)
                if heading:
                    current = {"number": heading.group(1), "title": heading.group(2).strip()}
                else:
                    current = {
                        "number": "Appendix %s" % appendix.group(1).upper(),
                        "title": appendix.group(2).strip() or "Appendix",
                    }
                current["body"] = []
                current["tables"] = []
                continue
            current["body"].append(text)  # type: ignore[union-attr]
        for i, table in enumerate(page_tables):
            if i < len(captions):
                caption = captions[i]
                walk_sections.last_caption = caption
                walk_sections.last_caption_page = number
            elif i == 0 and number == walk_sections.last_caption_page + 1:
                # A table continuing across a page break carries no caption of its own,
                # and that is the only case this fallback covers: the first table on the
                # page immediately after the one that last carried a caption. The chain
                # advances page by page, so Table 1 keeps its caption across all three
                # of its pages and stops at the first page that has no table to continue
                # it. Carrying the last caption to any uncaptioned table instead put five
                # rows of Table 2, comparable key strengths, into the corpus captioned as
                # Table 1's suggested cryptoperiods, nine pages and three sections later.
                # A row under the wrong caption is a misquote; a row with no caption is
                # dropped, which is the honest failure.
                caption = walk_sections.last_caption
                walk_sections.last_caption_page = number
            else:
                caption = ""
                walk_sections.uncaptioned += 1
            current["tables"].append({"caption": caption, "rows": table})  # type: ignore[union-attr]

    sections.append(current)
    return [s for s in sections if not _NOT_GUIDANCE.match(str(s["title"]))]


def sentence_records(sections: List[Dict[str, object]]) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for section in sections:
        body = " ".join(str(x) for x in section.get("body", []))  # type: ignore[union-attr]
        for sentence in _SENTENCE.split(body):
            sentence = mend_hyphen(re.sub(r"\s+", " ", sentence).strip())
            if len(sentence) < 45 or len(sentence) > 600:
                continue
            if sentence.count("(cid:") or sentence.count("  "):
                continue
            verb = _NORMATIVE.search(sentence)
            if not verb:
                continue
            params = parameters_in(sentence)
            if not params:
                continue
            records.append(
                {
                    "section_number": section["number"],
                    "section_title": section["title"],
                    "obligation": verb.group(1).upper(),
                    "parameters": params,
                    "kind": "statement",
                    "text": sentence,
                }
            )
    return records


# --------------------------------------------------------------------------
# Route 2 — parameter tables
# --------------------------------------------------------------------------


def table_records(
    sections: List[Dict[str, object]], wanted: List[str]
) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    if not wanted:
        return records
    for section in sections:
        for table in section.get("tables", []):  # type: ignore[union-attr]
            caption = _clean(table.get("caption"))
            if not caption or not any(w in caption.lower() for w in wanted):
                continue
            header, body = _normalise(table["rows"])
            if not body:
                continue
            for row in body:
                rendered = _render_row(header, row)
                if len(rendered) < 20:
                    continue
                params = parameters_in(" ".join(row)) or ["tabulated value"]
                records.append(
                    {
                        "section_number": section["number"],
                        "section_title": section["title"],
                        "obligation": "",
                        "parameters": params,
                        "kind": "table row",
                        "caption": caption,
                        "text": "%s — %s" % (caption, rendered),
                    }
                )
    return records


def _normalise(raw_rows: List[List[Optional[str]]]) -> Tuple[List[str], List[List[str]]]:
    """Drop empty columns and fold a multi-row header into one.

    These tables merge header cells vertically, so a heading arrives as two or three
    rows whose first column is empty. Treating each of those as a data row produces
    fragments like 'Period (OUP)' presented as a parameter.
    """
    rows = [[_clean(c) for c in row] for row in raw_rows]
    rows = [r for r in rows if any(r)]
    if len(rows) < 2:
        return [], []

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    rows = [[r[i] for i in keep] for r in rows]

    header_rows = [rows[0]]
    index = 1
    while index < len(rows) and not rows[index][0]:
        header_rows.append(rows[index])
        index += 1
    header = [
        " ".join(part for part in column if part).strip()
        for column in zip(*header_rows)
    ]
    return header, rows[index:]


def _render_row(header: List[str], row: List[str]) -> str:
    """Render a row as 'Column: value' pairs so it reads without the table around it."""
    parts = []
    for i, cell in enumerate(row):
        if not cell:
            continue
        label = header[i] if i < len(header) and header[i] else ""
        if i == 0:
            parts.append(cell)
        else:
            parts.append("%s: %s" % (label, cell) if label else cell)
    return "; ".join(parts)


# --------------------------------------------------------------------------


def extract(path: str, key: str) -> Tuple[List[Dict[str, object]], int, int]:
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        sections = walk_sections(pdf, _body_size(pdf))
        uncaptioned = walk_sections.uncaptioned
        wanted = WANTED_TABLES.get(key, [])
        records = table_records(sections, wanted)
        if not wanted:
            # No parameter table in this document, so the sentence route is all there
            # is. It is kept only where nothing else is available, because these PDFs
            # do not preserve word order reliably — 800-131A renders one requirement as
            # "the length of n be at least 224 bits to meet the minimum shall
            # security-strength requirement", with the verb displaced. A garbled
            # sentence quoted in a finding is worse than a stated gap, so what this
            # route returns is reported and left unloaded until it is checked by hand.
            records = sentence_records(sections)

    seen = set()
    unique = []
    for record in records:
        key = str(record["text"])[:140]
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique, pages, uncaptioned


def main() -> int:
    os.makedirs(CORPUS, exist_ok=True)
    os.makedirs(REVIEW, exist_ok=True)
    for doc in DOCS:
        path = os.path.join(DOCUMENTS, str(doc["file"]))
        if not os.path.exists(path):
            print("%-16s MISSING %s" % (doc["key"], doc["file"]))
            continue
        records, pages, uncaptioned = extract(path, str(doc["key"]))
        statements = [r for r in records if r["kind"] == "statement"]
        table_rows = [r for r in records if r["kind"] == "table row"]

        # Only a document this script actually parses tables out of is a corpus file it
        # owns. SP 800-88 is curated by tools/curate_800_88.py from a selector list, and
        # writing the sentence route over that path replaced 15 checked statements with
        # one unchecked sentence — silently, and only on the runs where this script went
        # last.
        owned = bool(WANTED_TABLES.get(str(doc["key"])))
        destination = CORPUS if owned else REVIEW
        with open(os.path.join(destination, "%s.json" % doc["key"]), "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "groups": [
                        {
                            "key": doc["group"],
                            "title": doc["title"],
                            "source_file": doc["file"],
                            "records": records,
                        }
                    ]
                },
                fh,
                indent=1,
                ensure_ascii=False,
            )
        sections = len({r["section_number"] for r in records})
        print(
            "%-16s %3dp  %3d records (%d sentences, %d table rows) across %2d sections%s"
            % (doc["key"], pages, len(records), len(statements), len(table_rows), sections,
               "" if owned else "   [review only, not loaded]")
        )
        if uncaptioned:
            # Named, because an uncaptioned table is dropped. Silence here is how five
            # rows of one table ended up under another table's caption.
            print("      %d table%s dropped for having no caption of their own"
                  % (uncaptioned, "" if uncaptioned == 1 else "s"))
        for record in (statements[:1] + table_rows[:1]):
            print("      §%-12s %s" % (record["section_number"], str(record["text"])[:96]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
