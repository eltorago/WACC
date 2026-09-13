"""Mending words a PDF broke across a line.

Extraction tooling, shared by the extractors so the rule lives in one place.

A PDF has no line-break character. An extractor that joins a wrapped line with a space
turns "enterprise-wide" into "enterprise- wide" and "need-to-know" into "need- to-know",
and those reach the corpus as the publisher's words when they are not. The round-trip
check against the source documents found ten of them across six extractors.

The hyphen is kept and the space removed, because every break of this kind in these
documents falls on a hyphen the publisher writes. Removing the hyphen as well would
invent "enterprisewide", which is neither what the document says nor what a reader would
search for.

One exception, and it is real English rather than an artefact. A suspended hyphen is
followed by "and" or "or" — SP 800-53 writes "security- and privacy-related
documentation", and closing that would produce "security-and". Those are left alone.
"""

import re
from typing import Iterable, List

_SUSPENDED = ("and", "or")
_BREAK = re.compile(r"(?<=[A-Za-z])-\s+(?=[a-z])")


def mend_hyphen(text: str) -> str:
    """Close a hyphen that a line break left with a space after it."""
    def close(match: re.Match) -> str:
        tail = text[match.end():].split(" ", 1)[0].strip(".,;:)")
        return "- " if tail.lower() in _SUSPENDED else "-"

    return _BREAK.sub(close, text or "")


def join_wrapped(parts: Iterable[str]) -> str:
    """Join a cell or paragraph's lines, mending anything broken at the join."""
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
    return mend_hyphen(joined)
