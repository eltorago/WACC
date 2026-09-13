"""Extract the C2M2 model domains, objectives and practices.

Extraction tooling. Not part of the shipped package.

The document states its own tolerance, which is what makes this checkable: "The C2M2
includes 356 cybersecurity practices, which are grouped into 10 domains" (section 4.1). A
run that does not land on 356 across 10 domains has parsed something else.

The layout is regular once read by position rather than by reading order, and reading
order is what makes it look irregular. Four things live in four x-bands at two sizes:

    x0 72,  size 12    an objective          "1. Manage IT and OT Asset Inventory"
    x0 77,  size 12    a maturity indicator  "MIL1"
    x0 121, size 10.5  a practice opener     "a. IT and OT assets that are..."
    x0 139, size 10.5  a practice continued  "in an ad hoc manner"

The MIL marker sits in the left margin a few points *below* the first line of the practice
it governs, so in reading order it arrives after that practice has already started. Sorting
by position and then asking, for each practice, which marker is nearest at or above it plus
a few points, puts the band boundary where the document draws it. Treating the marker as
"from here on" instead moves every band boundary down by one practice.

Which domain a page belongs to comes from the running header, which carries the short name
in parentheses on every page of the domain. The 6.x heading is used as corroboration, not
as the signal: two of the ten headings wrap onto a second line, so a parser that waits for
a heading loses ASSET and RESPONSE entirely.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pdfplumber

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCUMENTS = os.path.join(HERE, "data", "raw", "documents")
CORPUS = os.path.join(HERE, "data", "corpus")

SOURCE = "C2M2 Version 2.1 June 2022.pdf"
OUTPUT = os.path.join(CORPUS, "c2m2.json")

# Stated by the document in section 4.1. Not a guess and not a tolerance to relax.
STATED_PRACTICES = 356
STATED_DOMAINS = 10

# x-bands, in points, measured off the model domain pages.
OBJECTIVE_X = (68.0, 76.0)
MIL_X = (74.0, 84.0)
PRACTICE_X = (116.0, 126.0)
CONTINUATION_X = (134.0, 144.0)

BODY_SIZE = 10.5
HEADING_SIZE = 12.0

_HEADER_SHORT = re.compile(r"\(([A-Z][A-Z\-]{2,})\)\s*$")
_DOMAIN_HEADING = re.compile(r"^6\.(\d+)\s+(.+)$")
# The full stop after an objective number is not reliable: THREAD-3 reads "3 Management
# Activities for the THREAT domain" with no stop, and requiring one merged its eleven
# practices into objective 2 and gave six of them identifiers that already existed.
# Tolerating a bare number needs a second signal, so the number must be the one that comes
# next in this domain and the line must read as a heading rather than as prose.
_OBJECTIVE = re.compile(r"^(\d+)\.?\s+([A-Z]\S.*)$")
# A practice opener sometimes sits alone on its line with the text wrapped beneath it:
# PROGRAM-3b is the single token "b.".
_PRACTICE = re.compile(r"^([a-z])\.(?:\s+(\S.*))?$")
_MIL = re.compile(r"^MIL([123])$")
# Each domain's first page lists its objectives in the narrative, in the same face and at
# the same indent as the real headings — "the ASSET domain comprises five objectives:" and
# then 1 to 5. Reading those as headings left every practice in the domain labelled with
# the last objective number. The document separates the two itself: the practices follow a
# line reading "Objectives and Practices", and nothing before it is a heading.
_PRACTICES_START = "Objectives and Practices"
# Two dialects for the maturity marker, both in this document. On most pages it sits alone
# in the left margin. On others it shares a baseline with the practice it opens, so the
# line reads "MIL1 a. Risk responses ...", which is neither a marker nor a practice and was
# silently dropped along with the three practices under it.
_MIL_THEN_PRACTICE = re.compile(r"^MIL([123])\s+([a-z]\..*)$")
_NO_PRACTICE = re.compile(r"^(?:MIL[123]\s+)?No practice at MIL[123]$", re.IGNORECASE)


class Line:
    def __init__(self, words: List[dict]) -> None:
        self.words = words
        self.text = " ".join(w["text"] for w in words).strip()
        self.x0 = min(w["x0"] for w in words)
        self.top = min(w["top"] for w in words)
        self.size = max(round(w["size"], 1) for w in words)


def page_lines(page) -> List[Line]:
    buckets: Dict[int, List[dict]] = {}
    for word in page.extract_words(extra_attrs=["fontname", "size"]):
        buckets.setdefault(round(word["top"]), []).append(word)
    return [
        Line(sorted(buckets[top], key=lambda w: w["x0"])) for top in sorted(buckets)
    ]


def _within(value: float, band: Tuple[float, float]) -> bool:
    return band[0] <= value <= band[1]


def domain_of(lines: List[Line]) -> Optional[str]:
    """The domain short name, from the running header at the top of the page."""
    for line in lines:
        if line.top > 80:
            break
        match = _HEADER_SHORT.search(line.text)
        if match:
            return match.group(1)
    return None


def extract() -> Tuple[List[Dict[str, object]], Dict[str, object]]:
    path = os.path.join(DOCUMENTS, SOURCE)
    practices: List[Dict[str, object]] = []
    domains: List[Dict[str, object]] = []
    report: Dict[str, object] = {
        "pages": 0,
        "management_placeholders": 0,
        "unclassified": [],
        "headings": [],
    }

    with pdfplumber.open(path) as pdf:
        report["pages"] = len(pdf.pages)
        in_model = False
        current_domain: Optional[str] = None
        current_objective: Optional[Tuple[int, str]] = None
        current: Optional[Dict[str, object]] = None
        last_mil: List[Optional[int]] = [None]
        in_practices = False

        for index, page in enumerate(pdf.pages):
            lines = page_lines(page)
            text = page.extract_text() or ""
            if "6. MODEL DOMAINS" in text:
                in_model = True
            if in_model and re.search(r"^7\.\s+[A-Z]", text, re.MULTILINE):
                in_model = False
            if not in_model:
                continue

            short = domain_of(lines)
            if short and short != current_domain:
                current_domain = short
                current_objective = None
                current = None
                last_mil[0] = None
                in_practices = False
                domains.append({"short_name": short, "page": index + 1, "title": ""})

            # Corroboration only: the heading confirms the header's short name where it
            # is on one line, and is silent where it wraps.
            for line in lines:
                heading = _DOMAIN_HEADING.match(line.text.strip())
                if heading and line.size >= HEADING_SIZE and _within(line.x0, OBJECTIVE_X):
                    report["headings"].append((index + 1, line.text.strip()[:70]))

            markers: List[Tuple[float, int]] = []
            for line in lines:
                if not _within(line.x0, MIL_X):
                    continue
                stripped = line.text.strip()
                alone = _MIL.match(stripped)
                shared = _MIL_THEN_PRACTICE.match(stripped)
                if alone:
                    markers.append((line.top, int(alone.group(1))))
                elif shared:
                    markers.append((line.top, int(shared.group(1))))

            def mil_for(top: float) -> Optional[int]:
                # A band runs on across a page break, so a page whose practices all sit
                # above its first marker inherits the band from the page before. RISK-4d
                # and RISK-4e came out with no level at all without this.
                candidates = [m for t, m in markers if t <= top + 8.0]
                return candidates[-1] if candidates else last_mil[0]

            for line in lines:
                stripped = line.text.strip()
                if stripped == _PRACTICES_START and _within(line.x0, OBJECTIVE_X):
                    in_practices = True
                    current_objective = None
                    current = None
                    continue
                if not in_practices:
                    continue
                shared = _MIL_THEN_PRACTICE.match(stripped)
                if shared and _within(line.x0, MIL_X):
                    stripped = shared.group(2)
                elif _MIL.match(stripped) and _within(line.x0, MIL_X):
                    continue
                if _NO_PRACTICE.match(stripped):
                    report["management_placeholders"] += 1
                    current = None
                    continue

                objective = _OBJECTIVE.match(stripped)
                if (
                    objective
                    and line.size >= HEADING_SIZE
                    and _within(line.x0, OBJECTIVE_X)
                    and len(stripped) < 90
                    and not stripped.endswith(".")
                    and int(objective.group(1))
                    == (current_objective[0] + 1 if current_objective else 1)
                ):
                    current_objective = (int(objective.group(1)), objective.group(2))
                    current = None
                    continue

                practice = _PRACTICE.match(stripped)
                if practice and (
                    (_within(line.x0, PRACTICE_X) and abs(line.size - BODY_SIZE) < 0.6)
                    or shared
                ):
                    if current_domain is None or current_objective is None:
                        report["unclassified"].append((index + 1, stripped[:60]))
                        continue
                    mil = mil_for(line.top)
                    current = {
                        "domain": current_domain,
                        "objective_number": current_objective[0],
                        "objective": current_objective[1],
                        "letter": practice.group(1),
                        "identifier": "%s-%d%s"
                        % (current_domain, current_objective[0], practice.group(1)),
                        "mil": mil,
                        "page": index + 1,
                        "text": practice.group(2) or "",
                    }
                    practices.append(current)
                    last_mil[0] = mil
                    continue

                if (
                    current is not None
                    and _within(line.x0, CONTINUATION_X)
                    and abs(line.size - BODY_SIZE) < 0.6
                ):
                    current["text"] = ("%s %s" % (current["text"], stripped)).strip()
                    continue

                # Anything else on a model page that looks like body text and is not
                # narrative is worth seeing rather than dropping in silence.
                if (
                    line.top > 80
                    and _within(line.x0, PRACTICE_X)
                    and abs(line.size - BODY_SIZE) < 0.6
                ):
                    report["unclassified"].append((index + 1, stripped[:60]))

    report["domains"] = domains
    return practices, report


def main() -> int:
    practices, report = extract()
    by_domain: Dict[str, int] = {}
    for practice in practices:
        by_domain[str(practice["domain"])] = by_domain.get(str(practice["domain"]), 0) + 1

    print("C2M2 v2.1 — %d pages" % report["pages"])
    print("%d practices across %d domains (document states %d across %d)"
          % (len(practices), len(by_domain), STATED_PRACTICES, STATED_DOMAINS))
    for short, count in by_domain.items():
        print("   %-14s %3d" % (short, count))
    print("management-activity placeholders (No practice at MILn): %d"
          % report["management_placeholders"])
    if report["unclassified"]:
        print("unclassified lines on model pages: %d" % len(report["unclassified"]))
        for page, text in report["unclassified"][:8]:
            print("   p%-4d %s" % (page, text))

    missing_mil = [p for p in practices if p["mil"] is None]
    if missing_mil:
        print("practices with no maturity indicator level: %d" % len(missing_mil))
        for p in missing_mil[:6]:
            print("   %s" % p["identifier"])

    os.makedirs(CORPUS, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "key": "C2M2 Version 2.1",
                "title": "Cybersecurity Capability Maturity Model, Version 2.1",
                "source_file": SOURCE,
                "stated_practices": STATED_PRACTICES,
                "stated_domains": STATED_DOMAINS,
                "practices": practices,
            },
            handle,
            indent=1,
            ensure_ascii=False,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
