"""Extract normative parameter statements from the SP 800-63-4 family.

Extraction tooling. Not part of the shipped package.

Tier 5 exists to answer "what exactly is the number", so this does not take every
normative sentence. 800-63B alone contains 339 SHALL statements, and shipping all of
them would make the digital identity column a second control catalogue rather than a
specification. A statement is kept when it is normative *and* states a parameter — a
count, a period, a length, an algorithm or a rate.

That rule is mechanical and repeatable, which matters more than a hand-picked list:
someone can disagree with the rule and re-run it, but cannot audit a judgement that was
never written down.

Section numbers are reconstructed from the heading hierarchy. NIST's HTML carries the
top-level section in data-section and generates the rest with CSS, so the full number
has to be composed by counting headings within each top-level section.
"""

import html
import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(HERE, "data", "raw", "nist-800-63")
OUTPUT = os.path.join(HERE, "data", "corpus", "nist-800-63.json")

VOLUMES = [
    ("63A", "sp800-63a.html", "Identity Proofing and Enrollment"),
    ("63B", "sp800-63b.html", "Authentication and Authenticator Management"),
    ("63C", "sp800-63c.html", "Federation and Assertions"),
]

_HEADING = re.compile(r"<h([1-6])\b([^>]*)>(.*?)</h\1>", re.S)
_BLOCK = re.compile(r"<(p|li)\b[^>]*>(.*?)</\1>", re.S)
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

_NORMATIVE = re.compile(r"\b(SHALL NOT|SHOULD NOT|SHALL|SHOULD)\b")

# What makes a statement a parameter rather than a principle.
_PARAMETER_PATTERNS: List[Tuple[str, str]] = [
    ("period", r"\b\d+(?:\.\d+)?\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)\b"),
    ("length", r"\b\d+\s*(?:bits?|bytes?|characters?|digits?|octets?)\b"),
    ("bound", r"\b(?:at least|no more than|no fewer than|not exceed|a minimum of|a maximum of|greater than|less than)\s+\d"),
    ("rate", r"\b(?:1\s*in\s*\d|10\^\d|10\s*\^\s*\d|\d+\s*(?:attempts?|failures?|tries)\b)"),
    ("algorithm", r"\b(?:SHA-?\d+|AES(?:-\d+)?|RSA|ECDSA|EdDSA|HMAC|PBKDF2|Argon2|balloon hashing|TLS\s*1\.\d|approved cryptograph\w*|FIPS\s*140)\b"),
    ("entropy", r"\b\d+\s*bits? of (?:security|entropy)\b"),
]


def _text(fragment: str) -> str:
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", fragment))).strip()


def number_headings(source: str) -> List[Dict[str, object]]:
    """Return every heading with a composed section number and its span in the file."""
    headings: List[Dict[str, object]] = []
    counters: Dict[int, int] = {}
    current_top: Optional[str] = None

    for match in _HEADING.finditer(source):
        level = int(match.group(1))
        attrs = match.group(2)
        ds = re.search(r'data-section="([^"]*)"', attrs)
        title = _text(match.group(3))
        if not ds:
            continue
        top = ds.group(1)
        if top != current_top:
            current_top = top
            counters = {}
        if level == 1:
            number = top
        else:
            counters[level] = counters.get(level, 0) + 1
            for deeper in [l for l in counters if l > level]:
                counters[deeper] = 0
            parts = [top] + [
                str(counters[l]) for l in sorted(counters) if l <= level and counters[l]
            ]
            number = ".".join(parts)
        headings.append(
            {"level": level, "number": number, "title": title, "start": match.end()}
        )
    return headings


def parameters_in(text: str) -> List[str]:
    found = []
    for name, pattern in _PARAMETER_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE if name != "algorithm" else 0):
            found.append(name)
    return found


def extract_volume(path: str, volume: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        source = fh.read()

    headings = number_headings(source)
    bounds = [(h["start"], h) for h in headings]
    records: List[Dict[str, object]] = []
    seen = set()

    for match in _BLOCK.finditer(source):
        position = match.start()
        heading = None
        for start, candidate in bounds:
            if start <= position:
                heading = candidate
            else:
                break
        text = _text(match.group(2))
        if len(text) < 40:
            continue
        verb = _NORMATIVE.search(text)
        if not verb:
            continue
        params = parameters_in(text)
        if not params:
            continue
        key = text[:120]
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "volume": volume,
                "section_number": heading["number"] if heading else "",
                "section_title": heading["title"] if heading else "",
                "obligation": verb.group(1),
                "parameters": params,
                "text": text,
            }
        )
    return records


def main() -> int:
    volumes_out: List[Dict[str, object]] = []
    total = 0
    for volume, filename, title in VOLUMES:
        path = os.path.join(SOURCE_DIR, filename)
        if not os.path.exists(path):
            print("missing %s" % filename)
            continue
        records = extract_volume(path, volume)
        for i, record in enumerate(records, start=1):
            record["identifier"] = "%s §%s" % (
                volume,
                record["section_number"] or "?",
            )
            record["ordinal"] = i
        volumes_out.append(
            {"volume": volume, "title": title, "source_file": filename, "records": records}
        )
        total += len(records)
        by_verb: Dict[str, int] = {}
        for record in records:
            by_verb[str(record["obligation"])] = by_verb.get(str(record["obligation"]), 0) + 1
        print("%-5s %-46s %3d statements  %s" % (volume, title, len(records), by_verb))

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump({"volumes": volumes_out}, fh, indent=1, ensure_ascii=False)

    print("\ntotal %d" % total)
    for block in volumes_out:
        records: List[Dict[str, object]] = block["records"]  # type: ignore[assignment]
        for record in records[:2]:
            print("\n  [%s] %s  (%s)" % (record["identifier"], record["section_title"], ", ".join(record["parameters"])))
            print("     %s" % str(record["text"])[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
