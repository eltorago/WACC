"""Pull recommendations out of a CIS benchmark PDF into JSON.

Runs here, not on the locked-down machine: it needs pdfplumber. The JSON it writes is
what wacc/ reads with the standard library alone.

CIS text is import-only. This tool writes to data/corpus/detail/, which the packaging
check must refuse to ship; nothing it produces is redistributable.

The benchmarks are regular in a way the other PDFs are not. Every recommendation opens
with a dotted number, a profile level in parentheses and a title, and its body is a fixed
sequence of labelled blocks — Description, Rationale, Impact, Audit, Remediation, Default
Value, References, CIS Controls. That regularity is the only reason this is extraction
rather than curation, and the counts are checked against the registry's expected figures
so a parser change that silently loses half a document is caught.
"""

import argparse
import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

try:
    import pdfplumber
except ImportError:  # pragma: no cover - tooling only
    sys.exit("pdfplumber is required: pip install pdfplumber --break-system-packages")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTS = os.path.join(HERE, "data", "raw", "documents")
OUT = os.path.join(HERE, "data", "corpus", "detail")

# '1.21 (L1) Ensure 'Ephemeral profile' is set to 'Disabled' (Automated)'. The title can
# wrap, so the opener is matched and the rest is gathered until a labelled block starts.
# Two heading dialects, both real. Chrome, Edge and Office write the profile level into
# the heading — "1.21 (L1) Ensure 'Ephemeral profile' is set to 'Disabled' (Automated)".
# Windows 11, Microsoft 365 and Azure leave it out and state it below, under Profile
# Applicability. Requiring the inline level found two recommendations in a 1,341-page
# Windows benchmark and reported it as a tolerance miss.
_OPENER = re.compile(
    r"^(?P<id>\d+(?:\.\d+)+)\s+(?:\((?P<levels>L[12](?:\s*,\s*L[12])*|BL|NG)\)\s+)?"
    r"(?P<title>\S.*)$"
)

# Dropping the inline level makes the opener loose enough to match the CIS Controls
# mapping tables printed under every recommendation — "6.8 Define and Maintain Role-Based
# Access Control" has exactly that shape. A real recommendation is always followed within
# a few lines by its Profile Applicability block, so that is what confirms one.
_BLOCK = re.compile(
    r"^(Profile Applicability|Description|Rationale|Impact|Audit|Remediation|"
    r"Default Value|References|CIS Controls|Additional Information|MITRE ATT&CK Mappings)"
    r"\s*:\s*$"
)
_AUTOMATION = re.compile(r"\s*\((Automated|Manual)\)\s*$")
_LEVEL = re.compile(r"Level (\d) \((L\d)\)")

_CONFIRM = re.compile(r"^Profile Applicability\s*:\s*$")
_CONFIRM_WITHIN = 4

_PAGE_FURNITURE = re.compile(r"^(Page \d+|\d+ \| P a g e)$", re.I)


def _lines(path: str):
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                line = line.rstrip()
                if line and not _PAGE_FURNITURE.match(line.strip()):
                    yield line


def extract(path: str) -> list:
    lines = [line.strip() for line in _lines(path)]
    found = []
    current = None
    block = None
    for position, stripped in enumerate(lines):
        opener = _OPENER.match(stripped)
        confirmed = opener and any(
            _CONFIRM.match(lines[j])
            for j in range(position + 1, min(position + 1 + _CONFIRM_WITHIN, len(lines)))
        )
        if confirmed and not _BLOCK.match(stripped):
            title = opener.group("title")
            automated = _AUTOMATION.search(title)
            if current is not None:
                found.append(_finish(current))
            levels = opener.group("levels")
            current = {
                "identifier": opener.group("id"),
                "title": _AUTOMATION.sub("", title).strip(),
                "levels": [l.strip() for l in levels.split(",")] if levels else [],
                "assessment": automated.group(1) if automated else "",
                "blocks": {},
                "_open_title": automated is None,
            }
            block = None
            continue
        if current is None:
            continue
        label = _BLOCK.match(stripped)
        if label:
            block = label.group(1)
            current["blocks"].setdefault(block, [])
            current["_open_title"] = False
            continue
        if current["_open_title"]:
            # The title wrapped, or the automation marker sits on its own line.
            automated = _AUTOMATION.search(stripped)
            remainder = _AUTOMATION.sub("", stripped).strip()
            if remainder:
                current["title"] = (current["title"] + " " + remainder).strip()
            if automated:
                current["assessment"] = automated.group(1)
                current["_open_title"] = False
            continue
        if block:
            current["blocks"][block].append(stripped)
    if current is not None:
        found.append(_finish(current))
    return found


def _finish(entry: dict) -> dict:
    blocks = {k: " ".join(v).strip() for k, v in entry["blocks"].items()}
    applicability = blocks.get("Profile Applicability", "")
    levels = sorted({m.group(2) for m in _LEVEL.finditer(applicability)}) or entry["levels"]
    return {
        "identifier": entry["identifier"],
        "title": entry["title"],
        "profile_levels": levels,
        "assessment": entry["assessment"],
        "description": blocks.get("Description", ""),
        "rationale": blocks.get("Rationale", ""),
        "audit": blocks.get("Audit", ""),
        "remediation": blocks.get("Remediation", ""),
        "default_value": blocks.get("Default Value", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key", help="detail source key, e.g. cis-chrome")
    parser.add_argument("filename", help="PDF name under data/raw/documents")
    parser.add_argument("--platform", default="")
    parser.add_argument("--expected", type=int, default=0)
    args = parser.parse_args()

    path = os.path.join(DOCUMENTS, args.filename)
    if not os.path.exists(path):
        sys.exit("not found: %s" % path)

    records = extract(path)
    # A recommendation with no audit step is a heading that matched the opener, not a
    # recommendation. Dropping them here keeps the count honest.
    records = [r for r in records if r["audit"] or r["remediation"]]

    os.makedirs(OUT, exist_ok=True)
    out_path = os.path.join(OUT, "%s.json" % args.key)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "source_key": args.key,
                "platform": args.platform,
                "source_file": args.filename,
                "licence": "import-only",
                "recommendations": records,
            },
            fh,
            indent=1,
            ensure_ascii=False,
        )

    note = ""
    if args.expected:
        note = " (registry expects %d)" % args.expected
        if abs(len(records) - args.expected) > max(5, args.expected * 0.05):
            note += "  MISMATCH — check the parser before trusting this"
    print("%-14s %4d recommendations%s -> %s" % (args.key, len(records), note, out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
