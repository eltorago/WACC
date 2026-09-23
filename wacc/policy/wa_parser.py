"""Bounded WA policy structure parser, shared with the reviewed extraction approach."""
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pdfplumber
from .contracts import PolicyError

# The contents list draws its leaders with a font glyph carrying no Unicode
# mapping, so the text layer renders them as U+FFFD. Matching on full stops
# finds nothing at all here.
_LEADER = re.compile(r"[\ufffd\u00b7\u2022\u2026]{3,}|\.{4,}")
_FOOTER = re.compile(r"^\s*(\d+\s*\|\s*)?2024 WA Government Cyber Security Policy(\s*\|\s*\d+)?\s*$")
_TOC_ENTRY = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\.?\s+(.+?)\s*$")
_LETTERED = re.compile(r"^\s*([a-z])\.\s+(.*)$")
_FOOTNOTE = re.compile(r"^\s*\d+\s+[A-Z]")


def page_lines(pdf) -> List[str]:
    lines: List[str] = []
    for page in pdf.pages:
        text = page.extract_text(layout=True) or ""
        for raw in text.split("\n"):
            line = raw.rstrip()
            if not line.strip():
                continue
            if _FOOTER.match(line):
                continue
            lines.append(line)
    return lines


def parse_contents(lines: List[str]) -> Tuple[Dict[str, str], int]:
    """Return the numbered sections the contents list declares, and where it ends."""
    sections: Dict[str, str] = {}
    end = 0
    started = False
    for i, line in enumerate(lines):
        if line.strip() == "Contents":
            started = True
            continue
        if not started:
            continue
        if not _LEADER.search(line):
            # The contents list ends at the first line without dot leaders.
            if sections:
                end = i
                break
            continue
        cleaned = _LEADER.sub(" ", line).strip()
        m = _TOC_ENTRY.match(cleaned)
        if m:
            # Contents lines end with the page number the entry points at.
            number = m.group(1)
            if re.fullmatch(r"\d{4}", number):
                # 'A 2024 WA Government Cyber Security Policy' is a contents entry,
                # not a section numbered two thousand and twenty-four.
                continue
            title = re.sub(r"\s+\d{1,3}$", "", m.group(2)).strip()
            sections[number] = title
    return sections, end


_FUNCTION_LINE = re.compile(r"^([0-9])\.?\s+([A-Z][A-Za-z]+)$")


def find_functions(
    lines: List[str], wanted: Dict[str, str], contents: Dict[str, str]
) -> Dict[str, str]:
    """Name each function from wherever the document prints it.

    The contents list renders three of the six with dot leaders and three without, and
    the body prints the other three inside a two-column panel. Neither route alone sees
    all six, so both are read and the first name found wins.
    """
    roots = sorted({n.split(".")[0] for n in wanted})
    found: Dict[str, str] = {}
    for number in roots:
        if number in contents:
            found[number] = contents[number]
    for line in lines:
        m = _FUNCTION_LINE.match(line.strip())
        if m and m.group(1) in roots and m.group(1) not in found:
            found[m.group(1)] = m.group(2)
    return found


def split_sections(
    lines: List[str], numbers: Dict[str, str], start: int
) -> List[Dict[str, object]]:
    heading_at: List[Tuple[int, str, str]] = []
    for i in range(start, len(lines)):
        cleaned = lines[i].strip()
        m = _TOC_ENTRY.match(cleaned)
        if not m:
            continue
        number, rest = m.group(1), m.group(2).strip()
        expected = numbers.get(number)
        if not expected:
            continue
        # Titles wrap differently in the body, so compare on a prefix rather than
        # demanding the whole line match.
        head = expected.split()[0].lower()
        if not rest.lower().startswith(head):
            continue
        if "." not in number:
            # Function headings are decorative panels in this document and interleave
            # with a second column, so their titles come from the contents list
            # instead. Only numbered subsections carry requirements.
            continue
        heading_at.append((i, number, expected))

    # Unnumbered headings that follow the numbered sections. Without them the last
    # numbered section swallows the Exemptions text and presents it as a requirement.
    tail_headings = {"exemptions", "reporting", "review", "additional resources",
                     "further information"}
    tail_at = len(lines)
    if heading_at:
        for i in range(heading_at[-1][0] + 1, len(lines)):
            if lines[i].strip().lower() in tail_headings:
                tail_at = i
                break

    out: List[Dict[str, object]] = []
    for idx, (line_no, number, title) in enumerate(heading_at):
        stop = heading_at[idx + 1][0] if idx + 1 < len(heading_at) else tail_at
        body: List[str] = []
        for line in lines[line_no + 1 : stop]:
            if _FOOTNOTE.match(line) and len(line.strip()) > 40:
                continue
            body.append(line.strip())
        out.append({"number": number, "title": title, "body": body})
    return out


def build_records(sections: List[Dict[str, object]]) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for section in sections:
        number = str(section["number"])
        title = str(section["title"])
        body: List[str] = list(section["body"])  # type: ignore[arg-type]

        lead: List[str] = []
        items: List[Tuple[str, List[str]]] = []
        for line in body:
            m = _LETTERED.match(line)
            if m:
                items.append((m.group(1), [m.group(2)]))
            elif items:
                items[-1][1].append(line)
            else:
                lead.append(line)

        lead_text = " ".join(l for l in lead if l).strip()
        if items:
            for letter, parts in items:
                records.append(
                    {
                        "identifier": "%s%s" % (number, letter),
                        "section_number": number,
                        "section_title": title,
                        "lead_in": lead_text,
                        "text": " ".join(p for p in parts if p).strip(),
                    }
                )
        elif lead_text:
            records.append(
                {
                    "identifier": number,
                    "section_number": number,
                    "section_title": title,
                    "lead_in": "",
                    "text": lead_text,
                }
            )
    return records


def parse(path):
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > 100:
            raise PolicyError('Unsupported policy PDF.')
        lines = page_lines(pdf)
    if sum(len(line) for line in lines) > 2_000_000:
        raise PolicyError('Framework text exceeds supported limits.')
    cover = ' '.join(' '.join(lines[:10]).split())
    if not cover.startswith('Western Australian Government Cyber Security Policy 2024'):
        raise PolicyError('This parser requires the 2024 WA Government Cyber Security Policy.')
    numbers, toc_end = parse_contents(lines)
    sections = split_sections(lines, numbers, toc_end)
    records = build_records(sections)
    wanted = {n for n in numbers if '.' in n}
    if not wanted or wanted != {s['number'] for s in sections} or not records:
        raise PolicyError('Policy headings could not be fully extracted; keep the existing corpus and review this PDF manually.')
    return dict(title='Western Australian Government Cyber Security Policy 2024', records=records)
