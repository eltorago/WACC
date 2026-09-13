"""Extract the OAG WA better practice guides into a corpus JSON file.

Extraction tooling. Not part of the shipped package.

These guides put their recommendations inside two-column figure boxes, so flat text
extraction interleaves the columns line by line and produces sentences that never
existed. Font weight and x-position are what separate them: a box heading is Helvetica
Bold at 12 point, its description is Helvetica at 11, and the two columns sit either
side of the page midpoint. Body prose starts at the left margin, which is how it is
told apart from box content.
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
OUTPUT = os.path.join(HERE, "data", "corpus", "oag-wa.json")

REPORTS = [
    {
        "key": "report-12",
        "shape": "numbered",
        "file": "Report-12_Digital-Identity-and-Access-Management-Better-Practice-Guide.pdf",
        "title": "Digital Identity and Access Management",
        "report": "Report 12: 2023-24",
        "published": "2024-03-28",
    },
    {
        "key": "report-24",
        "shape": "figure-boxes",
        "file": "Report-24_-Security-Basics-for-Protecting-Critical-Infrastructure-from-Cyber-Threats.pdf",
        "title": "Security Basics for Protecting Critical Infrastructure from Cyber Threats",
        "report": "Report 24: 2022-23",
        "published": "2023-06-14",
    },
]

_SECTION = re.compile(r"^(\d+\.\d+)\s+(.*)$")
_SUBSECTION = re.compile(r"^(\d+\.\d+\.\d+)\s+(.+)$")
_CASE_STUDY = re.compile(r"^case study", re.IGNORECASE)
# Everything from the first appendix on is back matter: protocol glossaries, the
# Purdue model diagram and a table of previously tabled reports. None of it is guidance,
# and the report table in particular parses into convincing-looking nonsense.
_BACK_MATTER = re.compile(r"^(appendix|auditor general.s reports|date tabled)", re.IGNORECASE)
_BULLET = re.compile(r"^[•\u2022]\s*")
_BULLET_TERM = re.compile(r"^[•\u2022]\s*([A-Z][^–—-]{2,60}?)\s*[–—]\s*(.+)$")
_BODY_MARGIN = 100.0   # box content is indented; body prose starts at the left margin
_HEADING_SIZE = (11.5, 13.5)
_SECTION_SIZE = 14.0


class Line:
    def __init__(self, words: List[dict]) -> None:
        self.words = words
        self.text = " ".join(w["text"] for w in words).strip()
        self.x0 = min(w["x0"] for w in words)
        self.top = min(w["top"] for w in words)
        self.size = max(w["size"] for w in words)
        bold = sum(len(w["text"]) for w in words if "Bold" in w["fontname"])
        total = sum(len(w["text"]) for w in words) or 1
        self.bold = bold / total > 0.6

    def __repr__(self) -> str:
        return "Line(%.0f, %.1f, bold=%s, %r)" % (self.top, self.size, self.bold, self.text[:40])


def page_lines(page, x_min: float = 0.0, x_max: float = 10000.0) -> List[Line]:
    """Group words into lines within one horizontal band.

    The band matters. Two figure boxes side by side share a baseline, so grouping the
    whole page by y first splices a heading from the left column onto the heading from
    the right and produces a phrase that appears nowhere in the document.
    """
    words = [
        w
        for w in page.extract_words(extra_attrs=["fontname", "size"])
        if x_min <= w["x0"] < x_max
    ]
    buckets: Dict[int, List[dict]] = {}
    for word in words:
        buckets.setdefault(round(word["top"]), []).append(word)
    lines = []
    for top in sorted(buckets):
        row = sorted(buckets[top], key=lambda w: w["x0"])
        lines.append(Line(row))
    return lines


def is_box_heading(line: Line) -> bool:
    return (
        line.bold
        and _HEADING_SIZE[0] <= line.size <= _HEADING_SIZE[1]
        and line.x0 > _BODY_MARGIN
        and not line.text.lower().startswith("figure")
        and not line.text.lower().startswith("table")
    )


def is_box_body(line: Line) -> bool:
    return not line.bold and line.x0 > _BODY_MARGIN and line.size >= 9.5


def extract_report(path: str) -> Tuple[List[Dict[str, object]], int, str]:
    recommendations: List[Dict[str, object]] = []
    section_number: Optional[str] = None
    section_title: Optional[str] = None
    licence = ""

    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages):
            lines = page_lines(page)
            midpoint = page.width / 2.0
            column_lines = {
                "left": page_lines(page, 0.0, midpoint),
                "right": page_lines(page, midpoint, page.width),
            }
            if not licence:
                joined = " ".join(l.text for l in lines)
                m = re.search(r"©[^©]{0,240}?reproduced in whole or in part[^.]*\.", joined)
                if m:
                    licence = " ".join(m.group(0).split())

            # A section heading spans the full page, so it is read from the
            # unsplit lines; box content is read per column.
            if any(_BACK_MATTER.match(l.text) and l.bold for l in lines):
                break

            heading_tops = []
            for line in lines:
                if line.bold and line.size >= _SECTION_SIZE:
                    m = _SECTION.match(line.text)
                    if m:
                        heading_tops.append((line.top, m.group(1), m.group(2).strip()))

            columns: Dict[str, List[Line]] = {"left": [], "right": []}
            for side in ("left", "right"):
                for line in column_lines[side]:
                    if is_box_heading(line) or is_box_body(line):
                        columns[side].append(line)

            if heading_tops:
                # Boxes above the first section heading on this page belong to the
                # section that was open when the page started.
                first_top = heading_tops[0][0]
                before = {
                    side: [l for l in columns[side] if l.top < first_top]
                    for side in ("left", "right")
                }
                _flush(before, recommendations, section_number, section_title, page_index)
                section_number, section_title = heading_tops[-1][1], heading_tops[-1][2]
                columns = {
                    side: [l for l in columns[side] if l.top >= heading_tops[-1][0]]
                    for side in ("left", "right")
                }
            _flush(columns, recommendations, section_number, section_title, page_index)

    return recommendations, pages, licence


def _flush(
    columns: Dict[str, List[Line]],
    out: List[Dict[str, object]],
    section_number: Optional[str],
    section_title: Optional[str],
    page_index: int,
) -> None:
    if not section_number:
        return
    for side in ("left", "right"):
        heading: List[str] = []
        body: List[str] = []
        collecting_heading = False
        for line in columns[side]:
            if is_box_heading(line):
                if body and heading:
                    _emit(out, section_number, section_title, heading, body, page_index)
                    heading, body = [], []
                if not collecting_heading:
                    heading = []
                heading.append(line.text)
                collecting_heading = True
                continue
            collecting_heading = False
            if heading:
                body.append(line.text)
        if heading and body:
            _emit(out, section_number, section_title, heading, body, page_index)


def _emit(
    out: List[Dict[str, object]],
    section_number: str,
    section_title: Optional[str],
    heading: List[str],
    body: List[str],
    page_index: int,
) -> None:
    out.append(
        {
            "section_number": section_number,
            "section_title": section_title or "",
            "heading": " ".join(heading).strip(),
            "text": mend_hyphen(" ".join(body).strip()),
            "page": page_index + 1,
        }
    )


def extract_numbered(path: str) -> Tuple[List[Dict[str, object]], int, str]:
    """Parse a guide whose recommendations are numbered subsections of running text.

    Report 12 has no figure boxes. Its recommendations are 2.1.1, 2.1.2 and so on, set
    in body text at the left margin rather than in bold, so weight cannot be used to
    find them and the numbering has to.
    """
    records: List[Dict[str, object]] = []
    section_number: Optional[str] = None
    section_title: Optional[str] = None
    current: Optional[Dict[str, object]] = None
    body: List[str] = []
    licence = ""
    in_case_study = False

    def close() -> None:
        if current is not None:
            current["text"] = " ".join(body).strip()
            if current["text"]:
                records.append(dict(current))

    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for page_index, page in enumerate(pdf.pages):
            lines = page_lines(page)
            if not licence:
                joined = " ".join(l.text for l in lines)
                m = re.search(r"©[^©]{0,240}?reproduced in whole or in part[^.]*\.", joined)
                if m:
                    licence = " ".join(m.group(0).split())
            for line in lines:
                if line.size <= 9.5:
                    # Footnotes and the page footer, neither of which is guidance.
                    continue
                if line.bold and _BACK_MATTER.match(line.text):
                    close()
                    return records, pages, licence
                if line.bold and line.size >= _SECTION_SIZE:
                    m = _SECTION.match(line.text)
                    if m:
                        close()
                        current, body = None, []
                        section_number, section_title = m.group(1), m.group(2).strip()
                        in_case_study = False
                    continue
                if line.bold and _CASE_STUDY.match(line.text):
                    # Case studies illustrate the guidance; they state none of it.
                    in_case_study = True
                    continue
                m = _SUBSECTION.match(line.text)
                if m and line.x0 < _BODY_MARGIN:
                    close()
                    in_case_study = False
                    current = {
                        "section_number": section_number or m.group(1).rsplit(".", 1)[0],
                        "section_title": section_title or "",
                        "heading": m.group(2).strip(),
                        "subsection": m.group(1),
                        "page": page_index + 1,
                    }
                    body = []
                    continue
                if in_case_study:
                    continue
                if current is None:
                    # Section 2.2 carries its guidance as bullets rather than numbered
                    # subsections. Each bullet leads with the practice it names.
                    bullet = _BULLET_TERM.match(line.text)
                    if bullet and section_number:
                        close()
                        current = {
                            "section_number": section_number,
                            "section_title": section_title or "",
                            "heading": bullet.group(1).strip(),
                            "subsection": "",
                            "page": page_index + 1,
                        }
                        body = [bullet.group(2).strip()]
                        continue
                    if _BULLET.match(line.text):
                        continue
                    continue
                bullet = _BULLET_TERM.match(line.text)
                if bullet and not current.get("subsection"):
                    close()
                    current = {
                        "section_number": section_number or "",
                        "section_title": section_title or "",
                        "heading": bullet.group(1).strip(),
                        "subsection": "",
                        "page": page_index + 1,
                    }
                    body = [bullet.group(2).strip()]
                    continue
                body.append(line.text)
        close()

    return records, pages, licence


def main() -> int:
    data: Dict[str, object] = {"guides": []}
    total = 0
    for report in REPORTS:
        path = os.path.join(DOCUMENTS, str(report["file"]))
        if not os.path.exists(path):
            print("missing %s" % report["file"])
            continue
        if report.get("shape") == "numbered":
            recommendations, pages, licence = extract_numbered(path)
        else:
            recommendations, pages, licence = extract_report(path)
        prefix = str(report["report"]).split(":")[0].replace(" ", "-")
        ordinal: Dict[str, int] = {}
        for record in recommendations:
            section = str(record["section_number"])
            ordinal[section] = ordinal.get(section, 0) + 1
            # The guide's own subsection number where it has one, and a position
            # within the section where it does not. A running index across the whole
            # report would number the fourth item of 2.5 as 2.5.20.
            local = str(record.get("subsection") or "").strip()
            record["identifier"] = "%s %s" % (
                prefix,
                local or "%s.%d" % (section, ordinal[section]),
            )
        guides: List[Dict[str, object]] = data["guides"]  # type: ignore[assignment]
        guides.append(
            {
                "key": report["key"],
                "report": report["report"],
                "title": report["title"],
                "published": report["published"],
                "source_file": report["file"],
                "page_count": pages,
                "licence": licence,
                "records": recommendations,
            }
        )
        total += len(recommendations)
        sections = sorted({str(r["section_number"]) for r in recommendations})
        print("%-10s %2d pages  %3d recommendations across sections %s"
              % (report["key"], pages, len(recommendations), ", ".join(sections)))
        print("           licence: %s" % (licence[:96] or "NOT FOUND"))
        for record in recommendations[:2]:
            print("           %-34s | %s" % (str(record["heading"])[:34], str(record["text"])[:56]))

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
    print("\ntotal recommendations %d" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
