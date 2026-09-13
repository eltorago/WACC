"""Curated extract of SP 800-88 Rev 2, Guidelines for Media Sanitization.

Extraction tooling. Not part of the shipped package.

Rev 2 states almost nothing numeric, which is why the automatic parameter filter came
back empty on it. What it does state is categorical — clear, purge, destroy, and the
conditions under which cryptographic erase can be trusted. Media disposal is a topic
where the ISM, the WA CSP, the PSPF and 800-53 all impose something, so leaving this
document out would have left that comparison with nothing underneath it.

Curation here is a list of selectors, not typed-out text. Each selector names a section
and a distinctive phrase; the script finds the sentence containing that phrase in that
section and emits the document's own words. A selector that matches nothing, or matches
more than one sentence, fails the run. That makes the extract reproducible against a
future revision instead of frozen at whatever was true today.

One warning is carried into the corpus. This document abbreviates "information storage
media" as ISM. In this tool ISM means the Information Security Manual, and the two
appear in the same result set constantly.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

import pdfplumber

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textjoin import mend_hyphen  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_nist_pdf import _SENTENCE, parameters_in, walk_sections, _body_size  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(HERE, "data", "raw", "documents", "NIST.SP.800-88r2.pdf")
OUTPUT = os.path.join(HERE, "data", "corpus", "nist-800-88.json")

_KEYWORD = re.compile(r"\b(shall not|should not|must not|shall|should|must)\b", re.IGNORECASE)

# (section, distinctive phrase). The phrase identifies one sentence; it is never the
# text that gets stored.
SELECTORS: List[Tuple[str, str]] = [
    ("3.1.1", "applies logical techniques to sanitize data in all user-"),
    ("3.1.1", "a more secure sanitization method in the form of purge"),
    ("3.1.2", "make the recovery of target data infeasible using state-of-the-art"),
    ("3.1.2", "purge sanitization method should be used instead of the clear"),
    ("3.1.2", "Degaussing should not be used for non-magnetic"),
    ("3.1.3", "render target data recovery infeasible using state-of-the-art"),
    ("3.1.3", "Pulverize and shred techniques"),
    ("3.2", "encryption modules validated to the current FIPS-140 standard"),
    # One selector, not two. The document states the 128-bit strength floor and the
    # entropy floor as two bullets of a single sentence, so selecting each separately
    # returns the same sentence twice.
    ("3.2.1", "at least 128 bits"),
    ("3.2.2", "should not be trusted on ISM that have been backed up or escrowed"),
    ("3.2.3", "all copies of the target cryptographic keys"),
    ("3.2.4", "encryption modules that have been validated to the current FIPS-"),
    ("4.5.1", "sanitization results should be inspected"),
    ("4.5.2", "should result in the sanitization not being accepted"),
    ("4.6", "certificate of sanitization"),
]


def sentences_by_section(path: str) -> Dict[str, List[str]]:
    with pdfplumber.open(path) as pdf:
        sections = walk_sections(pdf, _body_size(pdf))
    out: Dict[str, List[str]] = {}
    titles: Dict[str, str] = {}
    for section in sections:
        number = str(section["number"])
        body = re.sub(r"\s+", " ", " ".join(str(x) for x in section.get("body", [])))
        pieces = [s.strip() for s in _SENTENCE.split(body) if len(s.strip()) > 30]
        out.setdefault(number, []).extend(pieces)
        titles.setdefault(number, str(section["title"]))
    sentences_by_section.titles = titles  # type: ignore[attr-defined]
    return out


def main() -> int:
    pool = sentences_by_section(SOURCE)
    titles = getattr(sentences_by_section, "titles", {})

    records: List[Dict[str, object]] = []
    failures: List[str] = []

    for section, phrase in SELECTORS:
        candidates = [s for s in pool.get(section, []) if phrase.lower() in s.lower()]
        if len(candidates) != 1:
            failures.append(
                "§%s / %r matched %d sentences" % (section, phrase, len(candidates))
            )
            continue
        text = candidates[0]
        if any(text == str(r["text"]) for r in records):
            failures.append(
                "§%s / %r resolved to a sentence another selector already took"
                % (section, phrase)
            )
            continue
        keyword = _KEYWORD.search(text)
        records.append(
            {
                "section_number": section,
                "section_title": titles.get(section, ""),
                "obligation": keyword.group(1).upper() if keyword else "",
                "parameters": parameters_in(text) or ["method"],
                "kind": "statement",
                "text": mend_hyphen(text),
            }
        )

    if failures:
        print("SELECTORS THAT DID NOT RESOLVE — nothing written:")
        for failure in failures:
            print("   %s" % failure)
        return 1

    with open(OUTPUT, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "revision": "Revision 2",
                "revision_source": "cover page",
                "groups": [
                    {
                        "key": "SP 800-88 Rev 2",
                        "title": "Guidelines for Media Sanitization",
                        "source_file": os.path.basename(SOURCE),
                        "note": (
                            "This publication abbreviates 'information storage media' "
                            "as ISM. In this tool ISM means the Information Security "
                            "Manual."
                        ),
                        "records": records,
                    }
                ],
            },
            fh,
            indent=1,
            ensure_ascii=False,
        )

    print("selectors resolved  %d of %d" % (len(records), len(SELECTORS)))
    sections = sorted({str(r["section_number"]) for r in records})
    print("sections            %s" % ", ".join(sections))
    for record in records:
        print("  §%-7s %-9s %s" % (record["section_number"], record["obligation"], str(record["text"])[:96]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
