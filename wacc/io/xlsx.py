"""Minimal xlsx reader, standard library only.

An xlsx is a zip of XML, so no third-party package is needed and the no-pip
constraint holds for importers as well as for the tool.

Returns cell values as strings. Nothing here interprets a workbook; callers do.
"""

import re
import zipfile
from typing import Dict, Iterator, List, Optional, Tuple
from xml.etree import ElementTree as ET

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKGREL = "http://schemas.openxmlformats.org/package/2006/relationships"

_CELL_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _q(tag: str, ns: str = _MAIN) -> str:
    return "{%s}%s" % (ns, tag)


def column_index(ref: str) -> int:
    """A -> 0, B -> 1, AA -> 26."""
    m = _CELL_REF.match(ref)
    letters = m.group(1) if m else ref
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


class Workbook:
    def __init__(self, path: str) -> None:
        self.path = path
        self._zip = zipfile.ZipFile(path)
        self._shared = self._read_shared_strings()
        self._sheets = self._read_sheet_index()

    # -- public -----------------------------------------------------------

    @property
    def sheet_names(self) -> List[str]:
        return [name for name, _ in self._sheets]

    def rows(self, sheet: Optional[str] = None) -> Iterator[List[str]]:
        """Yield each row as a list of strings, padded to the widest cell seen.

        Blank cells are empty strings. Merged cells carry their value in the
        top-left position only, which is how the file stores them.
        """
        target = sheet or self.sheet_names[0]
        part = dict(self._sheets).get(target)
        if part is None:
            raise KeyError("no sheet named %r in %s" % (target, self.path))
        data = self._zip.read(part)
        root = ET.fromstring(data)
        for row in root.iter(_q("row")):
            cells: Dict[int, str] = {}
            for c in row.findall(_q("c")):
                ref = c.get("r") or ""
                idx = column_index(ref) if ref else len(cells)
                cells[idx] = self._cell_value(c)
            if not cells:
                yield []
                continue
            width = max(cells) + 1
            yield [cells.get(i, "") for i in range(width)]

    def table(self, sheet: Optional[str] = None, header_row: int = 0) -> Tuple[List[str], List[List[str]]]:
        """Header list plus body rows, with body rows padded to header width."""
        all_rows = list(self.rows(sheet))
        if header_row >= len(all_rows):
            return [], []
        header = [h.strip() for h in all_rows[header_row]]
        body = []
        for r in all_rows[header_row + 1 :]:
            if not any(cell.strip() for cell in r):
                continue
            padded = list(r) + [""] * (len(header) - len(r))
            body.append(padded)
        return header, body

    # -- internals --------------------------------------------------------

    def _read_shared_strings(self) -> List[str]:
        try:
            data = self._zip.read("xl/sharedStrings.xml")
        except KeyError:
            return []
        root = ET.fromstring(data)
        out = []
        for si in root.findall(_q("si")):
            out.append(_si_text(si))
        return out

    def _read_sheet_index(self) -> List[Tuple[str, str]]:
        wb = ET.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ET.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        by_id = {}
        for rel in rels.findall(_q("Relationship", _PKGREL)):
            target = rel.get("Target") or ""
            if target.startswith("/"):
                target = target[1:]
            elif not target.startswith("xl/"):
                target = "xl/" + target
            by_id[rel.get("Id")] = target
        out = []
        for sheet in wb.iter(_q("sheet")):
            rid = sheet.get(_q("id", _REL))
            part = by_id.get(rid)
            if part:
                out.append((sheet.get("name") or "", part))
        return out

    def _cell_value(self, c: ET.Element) -> str:
        ctype = c.get("t")
        if ctype == "s":
            v = c.find(_q("v"))
            if v is None or not v.text:
                return ""
            try:
                return self._shared[int(v.text)]
            except (ValueError, IndexError):
                return ""
        if ctype == "inlineStr":
            is_el = c.find(_q("is"))
            return _si_text(is_el) if is_el is not None else ""
        v = c.find(_q("v"))
        return v.text or "" if v is not None else ""


def _si_text(el: ET.Element) -> str:
    """Concatenate the text runs of a shared-string or inline-string element."""
    parts = []
    for t in el.iter(_q("t")):
        parts.append(t.text or "")
    return "".join(parts)
