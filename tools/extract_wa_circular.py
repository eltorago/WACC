"""Extract Premier's Circular 2025/13 into a corpus JSON file.

Extraction tooling. Not part of the shipped package.

Two pages, three numbered measures, each with a short obligation list. The obligations
are the second-level bullets, so indentation is what separates a requirement from the
sentence that introduces it.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional

import pdfplumber

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(HERE, "data", "raw", "documents", "wa-premiers-circular-2025-13.pdf")
OUTPUT = os.path.join(HERE, "data", "corpus", "wa-circular.json")

_NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")
_BULLET = re.compile(r"^([•o●-])\s+(.*)$")
_STOP = re.compile(r"^(BACKGROUND|For enquiries contact|Other relevant Circulars)", re.IGNORECASE)
_FIELD = re.compile(r"^(Number|Issue Date|Review Date):\s*(.*)$")


def extract() -> Dict[str, object]:
    fields: Dict[str, str] = {}
    measures: List[Dict[str, object]] = []
    current: Optional[Dict[str, object]] = None
    pending_lead: Optional[str] = None
    stopped = False

    with pdfplumber.open(SOURCE) as pdf:
        pages = len(pdf.pages)
        raw_lines: List[str] = []
        for page in pdf.pages:
            text = page.extract_text(layout=True) or ""
            raw_lines.extend(text.split("\n"))

    for raw in raw_lines:
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = _FIELD.match(stripped)
        if m:
            fields[m.group(1)] = m.group(2).strip()
            continue
        if _STOP.match(stripped):
            stopped = True
        if stopped:
            continue

        indent = len(line) - len(line.lstrip())

        m = _NUMBERED.match(stripped)
        if m:
            current = {"number": m.group(1), "heading": m.group(2).strip(), "items": []}
            measures.append(current)
            pending_lead = None
            continue

        if current is None:
            continue

        b = _BULLET.match(stripped)
        if b:
            marker, text = b.group(1), b.group(2).strip()
            # A first-level bullet ending in a colon introduces the obligations that
            # follow; the obligations themselves are the deeper bullets.
            if marker in ("•", "-") and text.endswith(":"):
                pending_lead = text
                continue
            if marker in ("•", "-") and indent <= 12:
                pending_lead = None
                continue
            items: List[Dict[str, str]] = current["items"]  # type: ignore[assignment]
            items.append({"lead_in": pending_lead or "", "text": text})
            continue

        items = current["items"]  # type: ignore[assignment]
        if items:
            items[-1]["text"] = (items[-1]["text"] + " " + stripped).strip()

    records: List[Dict[str, object]] = []
    for measure in measures:
        items: List[Dict[str, str]] = measure["items"]  # type: ignore[assignment]
        for i, item in enumerate(items):
            records.append(
                {
                    "identifier": "%s%s" % (measure["number"], chr(ord("a") + i)),
                    "measure": measure["number"],
                    "measure_heading": measure["heading"],
                    "lead_in": item["lead_in"],
                    "text": item["text"],
                }
            )

    return {
        "source_file": os.path.basename(SOURCE),
        "title": "Premier's Circular 2025/13 — Cyber Security Measures for WA Government Entities",
        "page_count": pages,
        "fields": fields,
        "measures": [{"number": m["number"], "heading": m["heading"]} for m in measures],
        "records": records,
    }


def main() -> int:
    data = extract()
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)

    print("pages     %d" % data["page_count"])
    print("fields    %s" % data["fields"])
    print("measures  %d" % len(data["measures"]))
    print("records   %d" % len(data["records"]))
    for record in data["records"]:
        print("  %-4s %-46s %s" % (record["identifier"], record["measure_heading"][:46], record["text"][:74]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
