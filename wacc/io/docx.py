"""Minimal docx reader, standard library only.

A docx is a zip of XML, so legislation from the Federal Register of Legislation parses
here without a third-party package and without the extraction detour that PDFs need.

Returns paragraphs with their style names. Style is what carries the structure in these
documents — a section heading is a paragraph styled ActHead5, not a line that happens to
start with a number.
"""

import re
import zipfile
from typing import Dict, Iterator, List, NamedTuple, Optional
from xml.etree import ElementTree as ET

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    return "{%s}%s" % (_W, tag)


class Paragraph(NamedTuple):
    style: str
    text: str
    index: int


class Table(NamedTuple):
    rows: List[List[str]]
    index: int


class Document:
    def __init__(self, path: str) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path)
        self._style_names = self._read_style_names()

    def _read_style_names(self) -> Dict[str, str]:
        """Map style id to the human-readable name Word shows."""
        try:
            data = self._zip.read("word/styles.xml")
        except KeyError:
            return {}
        root = ET.fromstring(data)
        out: Dict[str, str] = {}
        for style in root.findall(_q("style")):
            style_id = style.get(_q("styleId"))
            name = style.find(_q("name"))
            if style_id and name is not None:
                out[style_id] = name.get(_q("val")) or style_id
        return out

    def paragraphs(self) -> Iterator[Paragraph]:
        data = self._zip.read("word/document.xml")
        root = ET.fromstring(data)
        body = root.find(_q("body"))
        if body is None:
            return
        index = 0
        for para in body.iter(_q("p")):
            text = _paragraph_text(para)
            style_id = _paragraph_style(para)
            style = self._style_names.get(style_id, style_id or "")
            yield Paragraph(style=style, text=text, index=index)
            index += 1

    def blocks(self) -> Iterator[object]:
        """Paragraphs and tables in document order.

        Tables matter here because a legislative table is the provision. CIRMP Rules
        s 8(4) discharges the cyber obligation by naming documents in a table, and
        flattening those cells into a run of paragraphs loses which condition attaches
        to which framework.
        """
        data = self._zip.read("word/document.xml")
        root = ET.fromstring(data)
        body = root.find(_q("body"))
        if body is None:
            return
        index = 0
        for child in body:
            if child.tag == _q("p"):
                yield Paragraph(
                    style=self._style_names.get(_paragraph_style(child) or "", _paragraph_style(child) or ""),
                    text=_paragraph_text(child),
                    index=index,
                )
                index += 1
            elif child.tag == _q("tbl"):
                yield Table(rows=self._table_rows(child), index=index)
                index += 1

    def _table_rows(self, table: ET.Element) -> List[List[str]]:
        rows: List[List[str]] = []
        for tr in table.findall(_q("tr")):
            cells: List[str] = []
            for tc in tr.findall(_q("tc")):
                texts = [_paragraph_text(p) for p in tc.findall(_q("p"))]
                cells.append(" ".join(t for t in texts if t).strip())
            rows.append(cells)
        return rows

    def style_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for para in self.paragraphs():
            counts[para.style] = counts.get(para.style, 0) + 1
        return counts


def _paragraph_style(para: ET.Element) -> Optional[str]:
    props = para.find(_q("pPr"))
    if props is None:
        return None
    style = props.find(_q("pStyle"))
    return style.get(_q("val")) if style is not None else None


def _paragraph_text(para: ET.Element) -> str:
    """Concatenate runs, honouring tabs and breaks as spaces.

    Word splits a sentence across runs whenever formatting changes, so joining run
    text without regard for tabs turns '8  Requirements' into '8Requirements'.
    """
    parts: List[str] = []
    for node in para.iter():
        tag = node.tag
        if tag == _q("t"):
            parts.append(node.text or "")
        elif tag in (_q("tab"), _q("br")):
            parts.append(" ")
        elif tag == _q("noBreakHyphen"):
            parts.append("-")
    return re.sub(r"[ \t ]+", " ", "".join(parts)).strip()
