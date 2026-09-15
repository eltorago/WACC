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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textjoin import mend_hyphen  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(
    HERE, "sources", "files",
    "Detecting and mitigating Active Directory compromises (September 2026).pdf",
)
OUTPUT = os.path.join(HERE, "data", "corpus", "asd-ad.json")

_GROUP = re.compile(r"^(Mitigating|Detecting|Hardening)\b.*", re.IGNORECASE)
_CHECKBOX = "☐"
_FOOTER = re.compile(
    r"^(?:\d+\s+)?Detecting and Mitigating .*Active Directory Compromises(?:\s+\d+)?$",
    re.I,
)

_PARAMETER = re.compile(
    r"\b\d+\s*(?:-?\s*character|bit|day|hour|minute|month|year)s?\b|\bminimum\b|\bat least\b",
    re.IGNORECASE,
)


def appendix_pages(pdf) -> Tuple[int, int]:
    start = end = -1
    for i, page in enumerate(pdf.pages):
        text = re.sub(r"\s+", " ", page.extract_text() or "")
        if (
            start < 0
            and "Appendix A" in text
            and "Active Directory security controls" in text
            and i > 10
        ):
            start = i
        elif start >= 0 and "Appendix B" in text and i > start:
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
            checkbox_words = [w for w in words if _CHECKBOX in w["text"]]
            # The 2026 layout draws checkboxes as vector rectangles; earlier editions
            # exposed them as text glyphs. Both mark the start of a mitigation row.
            checkbox_rects = [
                rect for rect in page.rects
                if 6 <= rect["width"] <= 12
                and 6 <= rect["height"] <= 12
                and rect["x0"] < 100
            ]
            checkboxes = sorted(
                [w["top"] for w in checkbox_words]
                + [rect["top"] for rect in checkbox_rects]
            )
            box_column = max(
                [w["x1"] for w in checkbox_words]
                + [rect["x1"] for rect in checkbox_rects]
                + [0.0]
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
                bold = sum(
                    len(w["text"])
                    for w in line
                    if "Bold" in w["fontname"] or "Heavy" in w["fontname"]
                )
                total = sum(len(w["text"]) for w in line) or 1
                if bold / total > 0.6 and _GROUP.match(text):
                    group = text
                    continue
                if line[0]["x0"] < box_column - 2:
                    continue
                if not checkboxes:
                    continue
                if checkbox_rects:
                    # In the 2026 layout each vector box starts at the first text line.
                    # Continuation lines belong to the most recent box, even when the
                    # following row is visually closer.
                    preceding = [box for box in checkboxes if box <= top + 3]
                    marker = max(preceding) if preceding else checkboxes[0]
                    distance = top - marker
                else:
                    # Earlier editions expose a checkbox glyph centred on its row, so
                    # the nearest marker is more reliable than the preceding one.
                    marker = min(checkboxes, key=lambda b: abs(b - top))
                    distance = abs(marker - top)
                if distance > 70:
                    # Too far from any box to be part of a checklist row. This is the
                    # sentence introducing the table, which otherwise attaches itself
                    # to the first mitigation and swallows it.
                    continue
                if records and records[-1].get("_marker") == (index, marker):
                    # Mended here as well as at the emit, because this is the join where
                    # a word broken at a line end actually meets its other half.
                    records[-1]["text"] = mend_hyphen(
                        (str(records[-1]["text"]) + " " + text).strip()
                    )
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
                        "text": mend_hyphen(text),
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
                "revision": "September 2026",
                "revision_source": "publisher attachment title and publication copyright page",
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
