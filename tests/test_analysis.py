"""Thresholds and the analysis payload. Every case names the defect it came from.

The threshold cases are the sharpest in the suite, because each of them inverts a
requirement when it is wrong rather than merely ranking something badly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.analysis import Disagreement, analyse, currency_of, gather  # noqa: E402
from wacc.build import build  # noqa: E402
from wacc.model import ObligationStrength, Provenance  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402
from wacc.thresholds import (  # noqa: E402
    AT_LEAST,
    AT_MOST,
    UNSTATED,
    compare,
    extract,
    stated_by,
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


def one(text):
    found = [t for t in extract(text, "test:1") if not t.restates]
    return found[0] if found else None


def run() -> int:
    check = Check()

    # -- reading a bound ---------------------------------------------------

    t = one("The period specified in the notice must not be shorter than 28 days.")
    check.expect(
        t is not None and t.bound is AT_LEAST and t.value == 28 and t.negated,
        "negation", "'must not be shorter than 28 days' is a minimum of 28 days",
        "read as an upper bound it turns a statutory floor into a ceiling",
    )

    t = one("The PMK caching period is not set to greater than 1440 minutes.")
    check.expect(
        t is not None and t.bound is AT_MOST and not t.negated,
        "negation", "'not set to greater than' is a ceiling and is not flipped twice",
        "the phrase carries its own negative; applying the negation again on top of it "
        "turned the ceiling into a floor",
    )

    # Two separate defences fixed the case above, and only one of them is load-bearing
    # on this corpus. Narrowing the negation window to the words before the matched
    # phrase is what stops the double flip; the third column of _BOUNDS, which marks a
    # phrase as carrying its own negative, never fires on any of the 4,917 controls
    # because no publisher puts a negation immediately in front of one. The wording here
    # is constructed for that reason, and it is the only thing in the suite that fails
    # if the column is dropped.
    t = one("Ensure the value is not set to no more than 60 seconds.")
    check.expect(
        t is not None and t.bound is AT_MOST,
        "negation", "a negation in front of a self-negating phrase does not flip it",
        "'no more than' already means at most; negating it a second time reported a "
        "ceiling as a floor",
    )

    t = one("Have a login authentication timeout of no more than 60 seconds.")
    check.expect(
        t is not None and t.bound is AT_MOST,
        "longest", "'no more than 60 seconds' is a ceiling, not 'more than'",
        "taking the comparator nearest the number instead of the longest one read the "
        "phrase as its own opposite",
    )

    t = one("Certificate templates are reviewed at least every three months.")
    check.expect(
        t is not None and t.bound is AT_MOST and t.cadence,
        "cadence", "'at least every three months' is a maximum gap",
        "a floor on how often is a ceiling on the interval, and the interval is what two "
        "frameworks are compared on",
    )

    t = one("Patches for vulnerabilities in online services are applied within two weeks.")
    check.expect(
        t is not None and t.value == 2 and t.unit == "week",
        "worded", "'within two weeks' is read as a quantity",
        "the ISM writes the Essential Eight patching windows in words, and a digits-only "
        "pattern missed every one of them",
    )

    t = one("A minimum notification period of one month by service providers.")
    check.expect(
        t is not None and t.bound is AT_LEAST and t.bound_inferred,
        "loose bound", "a bound word two words from the number still governs it, marked",
        "'a minimum notification period of one month' put two words between the bound "
        "and the quantity and came back unstated",
    )

    t = one("Approval Status of Algorithms — ≥ 112 bits of security strength.")
    check.expect(
        t is not None and t.bound is AT_LEAST,
        "symbols", "'≥ 112 bits' is read as a floor",
        "SP 800-131A states its tables with symbols and they came back unstated",
    )

    found = [x for x in extract("A lifetime of less than 24 hours (86400 seconds) is used.")]
    kept = [x for x in found if not x.restates]
    check.expect(
        len(found) == 2 and len(kept) == 1,
        "restatement", "a parenthetical restatement is marked, not counted twice",
        "one publisher quantity became two thresholds",
    )

    check.expect(
        extract("Employ guards 24 hours per day, 7 days per week.") == [],
        "rate", "'24 hours per day' is a rate, not a bound on a quantity",
    )

    # -- what a number governs ---------------------------------------------

    corpus, _ = build(verbose=False)

    ssh = corpus.control("ism:ism-484")
    clauses = [t.subject for t in stated_by(ssh)]
    check.expect(
        bool(clauses) and clauses[0].startswith("have a login authentication timeout"),
        "clause", "a flattened bullet list breaks at the bullet",
        "without it the whole SSH configuration came back as one clause and a 60-second "
        "login timeout was read as being about log retention",
    )

    row = corpus.control("nist-800-131a:sp 800-131a rev 2 §10#2")
    check.expect(
        all(t.classifies for t in stated_by(row)),
        "table", "'Key lengths < 112 bits; Disallowed' is a category, not a requirement",
        "read as a requirement it contradicted every minimum key length in the ISM",
    )

    # -- comparing ---------------------------------------------------------

    ceilings = extract("Report within 12 hours. Report within 72 hours.")
    comparisons = compare(ceilings)
    check.expect(
        len(comparisons) == 1
        and comparisons[0].strictest.value == 12
        and comparisons[0].loosest.value == 72,
        "compare", "among ceilings the smallest is strictest",
    )

    floors = extract("A key of at least 112 bits. A key of at least 256 bits.")
    comparisons = compare(floors)
    check.expect(
        comparisons and comparisons[0].strictest.value == 256,
        "compare", "among floors the largest is strictest",
        "one ordering for both senses compares a deadline against a key length",
    )

    mixed = extract("Report within 12 hours. Retain for at least 90 days.")
    comparisons = compare(mixed)
    check.expect(
        comparisons and comparisons[0].strictest is None and comparisons[0].note,
        "compare", "a set mixing ceilings and floors has no single strictest, and says so",
    )

    both = extract("A key of at least 112 bits. A password of at least 15 characters.")
    check.expect(
        len(compare(both)) == 2,
        "dimension", "bits and characters are separate dimensions",
        "both are 'lengths' in English and are not the same quantity",
    )

    calendar = compare(extract("Reviewed at least every 24 months."))
    check.expect(
        calendar and calendar[0].approximate,
        "calendar", "a comparison crossing months is marked approximate",
        "a month is not an exact number of hours and asserting one silently is a defect",
    )

    # -- the payload -------------------------------------------------------

    index = SearchIndex(corpus)
    subject = "how quickly must a cyber security incident be reported"
    payload = analyse(corpus, subject, gather(corpus, index, subject))

    check.expect(
        len(payload.bands) == 5,
        "bands", "every tier is present in the payload, including empty ones",
        "position in a diagram is an assertion and a missing row reads as a question "
        "never asked",
    )
    empty_payload = analyse(corpus, "", [])
    check.expect(
        any(band.is_empty for band in empty_payload.bands)
        and any("shown empty rather than omitted" in n for n in empty_payload.notes),
        "bands", "an empty tier is stated in the notes",
    )

    check.expect(
        payload.comparisons
        and payload.comparisons[0].strictest.value == 12
        and payload.comparisons[0].strictest.control_uid == "soci-act:s 30bc.1",
        "payload", "the strictest notification deadline is SOCI s 30BC(1) at 12 hours",
    )
    check.expect(
        bool(payload.disagreements) and not payload.incompatible_bounds,
        "payload",
        "different deadlines are reported as disagreements, not as conflicts",
        "twelve hours and seventy-two hours are different deadlines and both can be met",
    )
    # Built rather than found, because the corpus holds no incompatible pair on any of
    # the plan's topics, and a check that runs on an empty list has tested nothing.
    floor = extract("Retain records for at least 90 days.", "cis-controls:8.10")[0]
    ceiling = extract("Delete records within 24 hours.", "ism:ism-1813")[0]
    staged = Disagreement(dimension="time", left=floor, right=ceiling)
    check.expect(
        staged.bounds_are_incompatible
        and "cannot both be met if they govern the same" in staged.describe(corpus),
        "payload", "an incompatible pair is offered for reading, never asserted",
        "subject matching reaches topic level, and within one topic two numbers often "
        "govern different duties",
    )
    two_ceilings = Disagreement(
        dimension="time",
        left=extract("Report within 12 hours.", "soci-act:s 30bc.1")[0],
        right=extract("Report within 72 hours.", "wa-csp:5.1c")[0],
    )
    check.expect(
        not two_ceilings.bounds_are_incompatible,
        "payload", "two ceilings are never incompatible",
        "meeting the tighter one meets the looser, and calling that a clash would "
        "manufacture a finding",
    )
    classified = Disagreement(
        dimension="bits",
        left=extract("A key of at least 256 bits.", "ism:ism-1813")[0],
        right=stated_by(row)[0],
    )
    check.expect(
        not classified.bounds_are_incompatible,
        "payload", "a table category is never one half of an incompatible pair",
        "SP 800-131A's 'Key lengths < 112 bits; Disallowed' contradicted every ISM "
        "minimum in the corpus",
    )

    strength_note = [n for n in payload.notes if "not one scale" in n]
    check.expect(
        bool(strength_note),
        "strength", "the payload says obligation strength is not one scale",
    )
    check.expect(
        strength_note and "SOCI Act" not in strength_note[0].split("instead")[0],
        "strength",
        "a framework that states no keyword is not described as stating a baseline",
        "lumping the two produced a note saying the SOCI Act states an implementation "
        "group, which it does not",
    )

    ism = corpus.control("ism:ism-1683")
    currency = dict(currency_of(ism))
    check.expect(
        "Essential Eight maturity level" in currency
        and "classifications this control applies to" in currency,
        "currency", "the ISM's own tiering is reported under its own name",
        "rendering it as 'unknown' beside the SOCI Act's 'mandatory' reads as the ISM "
        "being weaker, when the ISM does not use that vocabulary",
    )

    # -- the analysis window is not the display window ---------------------

    shallow = analyse(corpus, "patching applications and operating systems",
                      [h.control for h in index.search(
                          "patching applications and operating systems", limit=25).hits])
    deep = analyse(corpus, "patching applications and operating systems",
                   gather(corpus, index, "patching applications and operating systems"))
    shallow_count = sum(len(c.thresholds) for c in shallow.comparisons)
    deep_count = sum(len(c.thresholds) for c in deep.comparisons)
    check.expect(
        shallow_count == 0 and deep_count > 10,
        "window",
        "the Essential Eight patching windows need the deeper analysis set (%d vs %d)"
        % (shallow_count, deep_count),
        "they rank around 110 for their own topic, so a payload built from the visible "
        "page reported that nobody states a patching timeframe",
    )

    off = [t for t in deep.off_subject]
    check.expect(
        all(t.control_uid for t in off),
        "window", "quantities governing something else are listed, not compared",
    )

    silent = payload.frameworks_silent
    check.expect(
        bool(silent) and all(
            not any(c.framework.key == f.key and c.controls
                    for b in payload.bands for c in b.coverage)
            for f in silent
        ),
        "coverage", "%d frameworks are reported as saying nothing on this subject"
        % len(silent),
        "a framework missing from the output reads as not asked rather than silent",
    )

    print("\nanalysis: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
