"""Pull CISA's Zero Trust Maturity Model into JSON, one record per function.

Runs here, not on the locked-down machine: it needs pdfplumber.

The maturity tables do not survive pdfplumber's table detection. It reports nine columns
where there are five, splits wrapped cells across rows, and loses the association between
a function and its stages. So this reads word positions instead. Every maturity table on
every page puts its five headers — Function, Traditional, Initial, Advanced, Optimal — at
the same x positions, and every word below belongs to the last column that starts at or
before it. That is a fact about the document rather than a guess about its layout, and it
is checked: the run reports the function count and the loader refuses a count that has
moved without anyone noticing.

A row continues across a page break. The stage text for the last function on a page often
finishes at the top of the next one, before that page's own header row, so the open row is
carried rather than closed at the page boundary.
"""

import argparse
import json
import os
import re
import sys
import warnings
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

try:
    import pdfplumber
except ImportError:  # pragma: no cover - tooling only
    sys.exit("pdfplumber is required: pip install pdfplumber --break-system-packages")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTS = os.path.join(HERE, "data", "raw", "documents")
OUT = os.path.join(HERE, "data", "corpus")

STAGES = ("Traditional", "Initial", "Advanced", "Optimal")
HEADERS = ("Function",) + STAGES

# The pillars and cross-cutting capabilities the functions sit under, in the document's
# own order. A function is attributed to the last pillar heading seen above it.
PILLARS = (
    "Identity",
    "Devices",
    "Networks",
    "Applications and Workloads",
    "Data",
)
CROSS_CUTTING = ("Visibility and Analytics", "Automation and Orchestration", "Governance")

# The pillars are numbered section headings — '5.1 Identity', '5.6 Cross-Cutting
# Capabilities' — and they sit on the same pages as the tables, not on their own. Looking
# for a bare pillar name on its own line found one heading in the whole document and
# attributed all 226 rows to it.
_PILLAR_LINE = re.compile(r"^5\.\d+\s+(.+?)\s*$")
# 'Access Management (New Function)', 'Resource Access (Formerly Data Access)'. The
# annotation is the document telling the reader what changed between v1 and v2; it is
# kept as a note rather than glued into the name.
_ANNOTATION = re.compile(r"\s*\((New Function|Formerly [^)]+)\)\s*$", re.I)
_FOOTER = re.compile(r"^\d+\s+TLP:CLEAR$|^TLP:CLEAR$", re.I)
# Footnotes and the running header start at x0 72, three points left of the Function
# column at 78. A six-point tolerance swallowed them into column zero and turned every
# footnote into a function: 'FIDO2 is a set of protocols developed in collaboration...'
# was reported as a zero trust function of the Identity pillar.
_TOLERANCE = 2.0

# Every cell in every maturity table is written 'Agency does X'. A bold line in the
# Function column whose stage cells do not start that way is the tail of a function name
# that wrapped — 'Access Management (New' then 'Function)', 'Visibility and Analytics'
# then 'Capability' — and opening a second row on it split one function into two.
_CELL_OPENS = re.compile(r"^(Agency|Agencies)\b")
_BOLD = "Bold"
_LINE_TOLERANCE = 3.0

# A footnote reference is a superscript digit and arrives as a word of its own, so the
# corpus read "Agency sets some policies 26 for the lifecycle" and "encryption for all
# applicable internal and 28 external traffic protocols". Both are the document's
# footnote numbers standing in the middle of a sentence, and the second one puts a bare
# quantity where the threshold reader can see it. Only a bare number set smaller than the
# body is dropped; FIDO2 and SHA-256 are words with digits in them and are left alone.
_BARE_NUMBER = re.compile(r"^\d{1,3}$")
FOOTNOTE_SIZE_GAP = 1.0


def _lines(page):
    """Words grouped into visual lines, each keeping its x position."""
    rows: Dict[int, List[dict]] = {}
    for word in page.extract_words(extra_attrs=["fontname", "size"]):
        key = round(word["top"] / _LINE_TOLERANCE)
        rows.setdefault(key, []).append(word)
    return [sorted(rows[k], key=lambda w: w["x0"]) for k in sorted(rows)]


def _body_size(pdf) -> float:
    """The size most of this document's words are set at, for spotting superscripts."""
    counts: Dict[float, int] = {}
    for page in pdf.pages[: min(20, len(pdf.pages))]:
        for word in page.extract_words(extra_attrs=["size"]):
            size = round(float(word["size"]), 1)
            counts[size] = counts.get(size, 0) + len(word["text"])
    return max(counts, key=lambda s: counts[s]) if counts else 11.0


def _join_lines(parts: List[str]) -> str:
    """Join a cell's lines, closing the gap where a word was broken at a line end.

    Every one of the twenty-two breaks in this document falls on a hyphen the document
    itself writes — enterprise-wide, password-less, on-premises, case-by-case,
    anomaly-based, network-connected. So the space is removed and the hyphen kept.
    Removing the hyphen as well would invent 'enterprisewide', which is not what CISA
    wrote and is not what a reader would search for.
    """
    joined = ""
    for part in parts:
        piece = " ".join((part or "").split())
        if not piece:
            continue
        if joined.endswith("-"):
            joined += piece
        elif joined:
            joined += " " + piece
        else:
            joined = piece
    return joined


def _header_columns(line) -> Optional[List[float]]:
    texts = [w["text"] for w in line]
    if all(h in texts for h in HEADERS):
        return [next(w["x0"] for w in line if w["text"] == h) for h in HEADERS]
    return None


def _column_of(word, starts: List[float]) -> int:
    """Which column a word belongs to, or -1 when it is left of the table entirely.

    Defaulting to column zero put every footnote and the running header into the Function
    column, because they begin at x0 72 and the table begins at 78. That is how 'FIDO2 is
    a set of protocols developed in collaboration' became part of a function name.
    """
    if word["x0"] < starts[0] - _TOLERANCE:
        return -1
    index = 0
    for position, start in enumerate(starts):
        if word["x0"] >= start - _TOLERANCE:
            index = position
    return index


def extract(path: str) -> List[dict]:
    records: List[dict] = []
    current: Optional[dict] = None
    pillar = ""

    with pdfplumber.open(path) as pdf:
        previous_was_table = False
        body_size = _body_size(pdf)
        for page in pdf.pages:
            lines = _lines(page)

            # A page is table content only if it carries the five headers. Letting the
            # column positions persist past the last table read every narrative page as
            # rows and turned 28 functions into 226.
            header_index = None
            starts = None
            for index, line in enumerate(lines):
                found = _header_columns(line)
                if found:
                    header_index, starts = index, found
                    break

            for index, line in enumerate(lines):
                text = " ".join(w["text"] for w in line).strip()
                if not text or _FOOTER.match(text):
                    continue
                pillar_line = _PILLAR_LINE.match(text)
                if pillar_line and len(text) < 60:
                    pillar = pillar_line.group(1).strip()
                    continue
                if starts is None or index == header_index:
                    continue
                # Above the header on a table page is the tail of the previous page's
                # last row; on the first table page there is nothing open to continue.
                if index < header_index and not previous_was_table:
                    continue

                buckets: Dict[int, List[str]] = {}
                for word in line:
                    column = _column_of(word, starts)
                    if column < 0:
                        continue
                    # Stage text never begins in the Function column, so anything there
                    # is either a function name or page furniture. Function names are the
                    # only bold text in the table, which is what separates them from a
                    # footnote or the running header that crept past the x tolerance.
                    if column == 0 and _BOLD not in (word.get("fontname") or ""):
                        continue
                    if (
                        column > 0
                        and _BARE_NUMBER.match(word["text"])
                        and body_size - float(word.get("size") or body_size)
                        > FOOTNOTE_SIZE_GAP
                    ):
                        continue
                    buckets.setdefault(column, []).append(word["text"])
                opener = " ".join(buckets.get(0, [])).strip()
                stage_text = {
                    stage: " ".join(buckets.get(i, [])).strip()
                    for i, stage in enumerate(STAGES, start=1)
                }
                has_stage = any(stage_text.values())

                bold = any(
                    _BOLD in (w.get("fontname") or "")
                    for w in line
                    if _column_of(w, starts) == 0
                )
                if not buckets:
                    continue
                opens_a_cell = any(
                    _CELL_OPENS.match(value) for value in stage_text.values() if value
                )

                # A bold line in the Function column opens a row when its own stage
                # cells start one — every cell is written 'Agency does X' — or when it
                # has no stage text at all and the row already open has had its opener.
                # Some functions put the name on one line and the stage text on the next
                # ('Automation and' / 'Orchestration Capability'), and some wrap the name
                # after the stage text has started ('Traffic Encryption' / '(Formerly
                # Encryption)'). One signal alone merges one pair or the other.
                # A name whose annotation wraps mid-bracket is still one name.
                # 'Application Access (Formerly Access' / 'Authorization)' split into two
                # functions because the second line's cells also began with 'Agency'.
                mid_bracket = current is not None and current["name"].count("(") > current[
                    "name"
                ].count(")")
                starts_row = bold and not mid_bracket and (
                    opens_a_cell
                    or (not has_stage and current is not None and current["opened"])
                )
                if opener and starts_row:
                    current = {
                        "pillar": pillar,
                        "name": opener,
                        "opened": opens_a_cell,
                        "stages": {stage: [] for stage in STAGES},
                    }
                    records.append(current)
                elif opener and current is not None:
                    # A function name that wrapped: 'Data Availability (New' then
                    # 'Function)'. Opening a second row on it split one function in two.
                    current["name"] = (current["name"] + " " + opener).strip()
                    if opens_a_cell:
                        current["opened"] = True
                    for stage, part in stage_text.items():
                        if part:
                            current["stages"][stage].append(part)
                    continue
                if current is None:
                    continue
                if opens_a_cell:
                    current["opened"] = True
                for stage, part in stage_text.items():
                    if part:
                        current["stages"][stage].append(part)

            if starts is not None:
                previous_was_table = True
            else:
                previous_was_table = False
                current = None

    out = []
    for record in records:
        name = " ".join(record["name"].split())
        annotation = _ANNOTATION.search(name)
        out.append(
            {
                "pillar": record["pillar"],
                "name": _ANNOTATION.sub("", name).strip(),
                "note": annotation.group(1) if annotation else "",
                "stages": {
                    stage: _join_lines(parts)
                    for stage, parts in record["stages"].items()
                },
            }
        )
    return [r for r in out if any(r["stages"].values()) and len(r["name"]) > 2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="zero_trust_maturity_model_v2_508.pdf")
    parser.add_argument("--expected", type=int, default=0)
    args = parser.parse_args()

    path = os.path.join(DOCUMENTS, args.file)
    if not os.path.exists(path):
        sys.exit("not found: %s" % path)

    records = extract(path)
    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, "ztmm.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "source_file": args.file,
                "publisher": "CISA",
                "title": "Zero Trust Maturity Model Version 2.0",
                "stages": list(STAGES),
                "functions": records,
            },
            fh,
            indent=1,
            ensure_ascii=False,
        )

    pillars = {}
    for record in records:
        pillars[record["pillar"] or "(none)"] = pillars.get(record["pillar"] or "(none)", 0) + 1
    note = ""
    if args.expected and len(records) != args.expected:
        note = "  EXPECTED %d — check the parser before trusting this" % args.expected
    print("ztmm  %d functions%s -> %s" % (len(records), note, out_path))
    for name, count in sorted(pillars.items()):
        print("   %-32s %d" % (name, count))
    return 0


if __name__ == "__main__":
    sys.exit(main())
