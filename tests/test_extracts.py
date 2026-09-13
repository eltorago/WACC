"""What the curated NIST extracts actually say, checked against the tables they name.

The corpus holds table rows from three NIST PDFs, and a table row is only as good as the
caption above it. Every case here names the defect it came from, and all of them came
from one run: SP 800-57's Table 2 caption shared its baseline with a full stop from the
paragraph above, so an anchored match missed it, and the fallback for a table continuing
across a page break carried Table 1's caption onto it instead — nine pages and three
sections later.

The result was not a gap. Five rows of comparable key strengths were in the corpus
captioned "Table 1: Suggested cryptoperiods for key types", and five paragraphs of
running prose that pdfplumber had reported as a one-column table were in there under the
same caption. A row under the wrong caption is a misquote, and a misquote is what this
tool exists not to produce.

The captions are written down here rather than read from the extraction tooling. Asking
the extractor which tables it meant to extract, and then asking whether it extracted
them, is one question.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "data", "corpus")

# The tables the curation names, written out. A caption in the corpus that is not on this
# list is a table nobody asked for; a caption on this list that is not in the corpus is a
# table that went missing.
EXPECTED_TABLES = {
    "nist-800-57pt1": [
        "Table 1: Suggested cryptoperiods for key types",
        "Table 2: Comparable security strengths of symmetric block cipher and "
        "asymmetric-key algorithms",
        "Table 3: Maximum security strengths for hash and hash-based functions",
        "Table 4: Security strength time frames",
    ],
    "nist-800-131a": [
        "Table 1: Approval Status of Symmetric Algorithms Used for",
        "Table 2: Approval Status of Algorithms Used",
        "Table 3: Approval Status of Algorithms Used",
        "Table 4: Approval Status for SP 800-56A Key",
        "Table 5: Approval Status for the RSA-based Key",
        "Table 6: Approval Status of Block Cipher Algorithms",
        "Table 7: Approval Status of the Algorithms Used",
        "Table 8: Approval Status of Hash Functions",
        "Table 9: Approval Status of MAC Algorithms",
    ],
}

# Key-size notation. A cryptoperiod table states durations; this is what Table 2 states,
# and finding it under Table 1's caption is the exact shape of the misattribution.
KEY_SIZE = re.compile(r"\b[Lkfn]\s*=\s*\d+")

# Two sentences in one cell. The five prose rows read "...currently known methods.
# Advances in factoring..." — a paragraph, not a row.
PROSE = re.compile(r"[a-z]\.\s+[A-Z]")

# A footnote marker welded to a time unit: '< 2 years61' stated a cryptoperiod that the
# threshold reader could not see at all.
WELDED = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:second|minute|hour|day|week|month|year)s?\d{1,3}\b", re.I
)


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def expect(self, condition, area, detail, why=""):
        if condition:
            print("  pass  %-11s %s" % (area, detail))
        else:
            self.failed += 1
            print("  FAIL  %-11s %s" % (area, detail))
            if why:
                print("        from: %s" % why)


def _records(key):
    with open(os.path.join(CORPUS, "%s.json" % key), encoding="utf-8") as handle:
        return json.load(handle)["groups"][0]


def _body(record):
    text = record["text"]
    return text.split(" — ", 1)[1] if " — " in text else text


def run() -> int:
    check = Check()
    checked = 0

    for key, expected in sorted(EXPECTED_TABLES.items()):
        group = _records(key)
        rows = [r for r in group["records"] if r["kind"] == "table row"]
        checked += len(rows)
        captions = {r.get("caption", "") for r in rows}

        missing = [
            caption for caption in expected
            if not any(c.startswith(caption) for c in captions)
        ]
        check.expect(
            not missing, "present",
            "%s holds all %d tables the curation names" % (key, len(expected)),
            "missing: %s" % "; ".join(missing[:2]),
        )
        unexpected = [
            c for c in captions
            if not any(c.startswith(caption) for caption in expected)
        ]
        check.expect(
            not unexpected, "present",
            "%s holds no table the curation did not name" % key,
            "unexpected: %s" % "; ".join(unexpected[:2]),
        )
        check.expect(
            bool(rows), "present", "%s holds %d table rows to check" % (key, len(rows)),
            "a rule that runs over no rows has checked nothing",
        )

        # -- a row belongs to the table above it -----------------------------

        prose = [r for r in rows if PROSE.search(_body(r))]
        check.expect(
            not prose, "attribution",
            "%s: no stored row is running prose" % key,
            "five paragraphs of narrative were reported as a one-column table and "
            "stored as suggested cryptoperiods: %s"
            % (_body(prose[0])[:60] if prose else ""),
        )
        separatorless = [r for r in rows if ";" not in _body(r)]
        check.expect(
            not separatorless, "attribution",
            "%s: every stored row has more than one cell" % key,
            "a single-cell row is a page artefact, not a table row: %s"
            % (_body(separatorless[0])[:60] if separatorless else ""),
        )
        welded = [r for r in rows if WELDED.search(_body(r))]
        check.expect(
            not welded, "figures",
            "%s: no figure has a footnote marker welded to its unit" % key,
            "'< 2 years61' states a cryptoperiod and reads as no quantity at all: %s"
            % (_body(welded[0])[:60] if welded else ""),
        )

    # -- the two tables that must not be confused with each other ------------

    rows = [r for r in _records("nist-800-57pt1")["records"] if r["kind"] == "table row"]
    cryptoperiods = [r for r in rows if r["caption"].startswith("Table 1:")]
    strengths = [r for r in rows if r["caption"].startswith("Table 2:")]
    check.expect(
        bool(cryptoperiods) and not any(KEY_SIZE.search(_body(r)) for r in cryptoperiods),
        "attribution", "no cryptoperiod row states a key size (%d rows)"
        % len(cryptoperiods),
        "Table 2's rows were stored under Table 1's caption, so the corpus said "
        "'L = 15360' was a suggested cryptoperiod",
    )
    check.expect(
        bool(strengths) and all(KEY_SIZE.search(_body(r)) for r in strengths),
        "attribution", "every comparable-strength row states a key size (%d rows)"
        % len(strengths),
        "the same swap in the other direction, and a check that only looks one way "
        "passes when both tables are empty",
    )

    # -- one tool owns one corpus file ---------------------------------------

    sanitisation = _records("nist-800-88")
    check.expect(
        "note" in sanitisation and "information storage media" in sanitisation["note"],
        "ownership", "800-88 is the curated extract, carrying its own warning",
        "tools/extract_nist_pdf.py also had SP 800-88 in its document list and wrote "
        "the same path, replacing 15 checked statements with one unchecked sentence on "
        "whichever run went last",
    )
    check.expect(
        len(sanitisation["records"]) > 5,
        "ownership", "800-88 holds %d curated statements"
        % len(sanitisation["records"]),
        "the clobbered file held exactly one",
    )
    check.expect(
        not os.path.exists(os.path.join(CORPUS, "fips-140-3.json")),
        "ownership", "the sentence route's output is not in data/corpus",
        "unchecked extracts sitting beside checked ones is how one gets loaded",
    )

    print("\nextracts: %d failed (%d rows checked)" % (check.failed, checked))
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
