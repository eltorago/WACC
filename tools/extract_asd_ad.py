"""Extract ASD's Active Directory mitigations into a corpus JSON file.

Extraction tooling. Not part of the shipped package.

The guide's Appendix A is a checklist table, one row per mitigation, grouped by the
compromise it defends against. That checklist is the corpus; the body of the guide is
narrative around it.

The checkbox glyphs sit in their own narrow column, so reading the page line by line
interleaves a checkbox into the middle of the sentence beside it and splits mitigations
in half. Each checkbox marks where a mitigation starts, and the text column is read
separately and attached to the checkbox nearest it.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pdfplumber

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(
    HERE, "data", "raw", "documents",
    "Detecting and mitigating Active Directory compromises (January 2025).pdf",
)
OUTPUT = os.path.join(HERE, "data", "corpus", "asd-ad.json")

_APPENDIX_A = "Appendix A – Active Directory security controls"
_APPENDIX_B = "Appendix B"
_GROUP = re.compile(r"^(Mitigating|Detecting|Hardening)\b.*", re.IGNORECASE)
_CHECKBOX = "☐"
_FOOTER = re.compile(r"^Detecting and Mitigating .*Active Directory Compromises\s*\d*$", re.I)

_PARAMETER = re.compile(
    r"\b\d+\s*(?:-?\s*character|bit|day|hour|minute|month|year)s?\b|\bminimum\b|\bat least\b",
    re.IGNORECASE,
)


def appendix_pages(pdf) -> Tuple[int, int]:
    start = end = -1
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if start < 0 and _APPENDIX_A in text and i > 10:
            start = i
        elif start >= 0 and _APPENDIX_B in text and i > start:
            end = i
            break
    return start, (end if end > 0 else len(pdf.pages))


def extract() -> Tuple[List[Dict[str, object]], int]:
    records: List[Dict[str, object]] = []
    with pdfplumber.open(SOURCE) as pdf:
        pages = len(pdf.pages)
        start, end = appendix_pages(pdf)
        if start < 0:
            return [], pages

        group: Optional[str] = None
        for index in range(start, end):
            page = pdf.pages[index]
            words = page.extract_words(extra_attrs=["fontname", "size"])
            checkboxes = sorted(w["top"] for w in words if _CHECKBOX in w["text"])
            box_column = max(
                (w["x1"] for w in words if _CHECKBOX in w["text"]), default=0.0
            )

            # Group headings are bold and sit at the left margin, ahead of the boxes.
            rows: Dict[int, List[dict]] = {}
            for word in words:
                if _CHECKBOX in word["text"]:
                    continue
                if word["size"] < 9.5:
                    continue
                rows.setdefault(round(word["top"]), []).append(word)

            for top in sorted(rows):
                line = sorted(rows[top], key=lambda w: w["x0"])
                text = " ".join(w["text"] for w in line).strip()
                if not text or _FOOTER.match(text):
                    continue
                bold = sum(len(w["text"]) for w in line if "Bold" in w["fontname"])
                total = sum(len(w["text"]) for w in line) or 1
                if bold / total > 0.6 and _GROUP.match(text):
                    group = text
                    continue
                if line[0]["x0"] < box_column - 2:
                    continue
                if not checkboxes:
                    continue
                # The checkbox is centred on its row, so it can fall between the two
                # wrapped lines of the mitigation it marks. Reading order therefore
                # puts a box after the first line of its own row, and "the box above
                # this line" attaches every continuation to the wrong mitigation.
                # Nearest box wins instead.
                marker = min(checkboxes, key=lambda b: abs(b - top))
                if abs(marker - top) > 26:
                    # Too far from any box to be part of a checklist row. This is the
                    # sentence introducing the table, which otherwise attaches itself
                    # to the first mitigation and swallows it.
                    continue
                if records and records[-1].get("_marker") == (index, marker):
                    records[-1]["text"] = (str(records[-1]["text"]) + " " + text).strip()
                    continue
                records.append(
                    {
                        # The compromise being mitigated is the section here. Using
                        # "Appendix A" for every row would collapse seventeen
                        # techniques into one undifferentiated list.
                        "section_number": group or "Active Directory security controls",
                        "section_title": group or "Active Directory security controls",
                        "obligation": "",
                        "parameters": ["mitigation"],
                        "kind": "statement",
                        "text": text,
                        "_marker": (index, marker),
                    }
                )

    for record in records:
        record.pop("_marker", None)
        if _PARAMETER.search(str(record["text"])):
            record["parameters"] = ["mitigation", "bound"]
    return [r for r in records if len(str(r["text"])) > 25], pages


def main() -> int:
    records, pages = extract()
    if not records:
        print("no mitigations found — Appendix A did not resolve")
        return 1

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "revision": "January 2025",
                "revision_source": "cover page, 'Last updated'",
                "groups": [
                    {
                        "key": "Appendix A",
                        "title": "Active Directory security controls checklist",
                        "source_file": os.path.basename(SOURCE),
                        "records": records,
                    }
                ],
            },
            fh,
            indent=1,
            ensure_ascii=False,
        )

    groups = sorted({str(r["section_title"]) for r in records})
    print("pages           %d" % pages)
    print("mitigations     %d across %d groups" % (len(records), len(groups)))
    with_param = sum(1 for r in records if "bound" in r["parameters"])
    print("stating a bound %d" % with_param)
    for record in records[:5]:
        print("   %-38s %s" % (str(record["section_title"])[:38], str(record["text"])[:80]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
