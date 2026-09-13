"""Extract the PSPF List of Requirements into a corpus JSON file.

Extraction tooling, not part of the shipped package. Anything under tools/ may use
libraries that are not in the standard library; wacc/ may not. The output is JSON,
which wacc/ reads with the standard library alone.

The PDF is a ruled table, so the ruling lines are what define the cells. Nothing here
reflows text by x-coordinate guesswork.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textjoin import mend_hyphen  # noqa: E402
from typing import Dict, List, Optional

import pdfplumber

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(HERE, "data", "raw", "documents", "pspf-list-of-requirements.pdf")
OUTPUT = os.path.join(HERE, "data", "corpus", "pspf.json")

SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}

EXPECTED_COLUMNS = [
    "Req Number",
    "Release 26 Requirement",
    "Domain",
    "Section",
    "Applicability",
    "Start Date",
    "Status Decision",
    "Question Type",
    "Mandatory",
    "Scored",
]


def _clean(value: Optional[str]) -> str:
    """Cell text, with anything the table broke across a line mended.

    A requirement read "identify and manage the entity's internet- facing systems", which
    is the table wrapping inside a cell rather than anything the PSPF wrote.
    """
    return mend_hyphen(" ".join((value or "").split()))


def _find_header(rows: List[List[Optional[str]]]) -> Optional[int]:
    for i, row in enumerate(rows):
        if _clean(row[0]).lower().startswith("req number"):
            return i
    return None


def extract() -> Dict[str, object]:
    records: List[Dict[str, object]] = []
    header: List[str] = []
    title = ""

    with pdfplumber.open(SOURCE) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            tables = page.extract_tables(SETTINGS)
            if not tables:
                continue
            rows = tables[0]
            start = 0
            head = _find_header(rows)
            if head is not None:
                if not header:
                    header = [_clean(c) for c in rows[head]]
                    for candidate in rows[:head]:
                        text = _clean(candidate[0]) or _clean(
                            candidate[1] if len(candidate) > 1 else ""
                        )
                        if "List of Requirements" in text:
                            title = text
                start = head + 1
            for row in rows[start:]:
                number = _clean(row[0])
                if not number or not number.isdigit():
                    continue
                record: Dict[str, object] = {"req_number": number}
                for i, name in enumerate(header):
                    if i == 0 or i >= len(row):
                        continue
                    value = _clean(row[i])
                    if value:
                        record[name] = value
                records.append(record)

    return {
        "source_file": os.path.basename(SOURCE),
        "title": title,
        "page_count": page_count,
        "columns": header,
        "records": records,
    }


def main() -> int:
    data = extract()
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)

    numbers = [int(r["req_number"]) for r in data["records"]]
    missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers)) if numbers else []
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})

    print("title      %s" % data["title"])
    print("pages      %d" % data["page_count"])
    print("columns    %s" % ", ".join(data["columns"]))
    print("records    %d (highest requirement number %d)" % (len(numbers), max(numbers) if numbers else 0))
    print("gaps       %s" % (missing if missing else "none"))
    print("duplicates %s" % (duplicates if duplicates else "none"))
    if data["records"]:
        print("\nfirst record:")
        for k, v in data["records"][0].items():
            print("   %-46s %s" % (k[:46], str(v)[:70]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
