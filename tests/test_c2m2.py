"""C2M2, and the two provisions that name it.

Every case names the defect it came from, and the parser produced seven wrong answers
before it produced 356. The document states its own totals in section 4.1 — "The C2M2
includes 356 cybersecurity practices, which are grouped into 10 domains" — and that
figure is written down here rather than read from the extract, because asking the
extractor how many practices it meant to find and then asking how many it found is one
question.

The maturity indicator level is not decoration. s 8(4) names C2M2 at MIL1 and s 8A(3)
names Version 2.1 at MIL2, so a practice without its level cannot be read against either
provision, and the two provisions are not interchangeable.
"""

import os
import string
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.analysis import currency_of  # noqa: E402
from wacc.build import build  # noqa: E402
from wacc.model import LinkKind, Licence, Provenance  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402
from wacc.terms import named_set  # noqa: E402

# Stated by the document in section 4.1.
STATED_PRACTICES = 356
STATED_DOMAINS = 10
LEVELS = ("MIL1", "MIL2", "MIL3")


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


def run() -> int:
    corpus, _ = build(verbose=False)
    check = Check()

    controls = [c for c in corpus.controls.values() if c.framework_key == "c2m2"]
    practices = [c for c in controls if c.depth == 2]
    objectives = [c for c in controls if c.depth == 1]
    domains = [c for c in controls if c.depth == 0]

    # -- the document's own totals ------------------------------------------

    check.expect(
        len(practices) == STATED_PRACTICES,
        "totals", "%d practices, which is what section 4.1 states" % len(practices),
        "351 was a missing full stop after an objective number, 356 with duplicate "
        "identifiers was the narrative list of objectives being read as headings",
    )
    check.expect(
        len(domains) == STATED_DOMAINS,
        "totals", "%d domains, which is what section 4.1 states" % len(domains),
        "the domain comes from the running header; two of the ten 6.x headings wrap "
        "onto a second line and a parser waiting for a heading loses ASSET and RESPONSE",
    )
    check.expect(
        len(objectives) == 43,
        "totals", "%d objectives across the ten domains" % len(objectives),
    )

    # -- structure -----------------------------------------------------------

    identifiers = [c.identifier for c in practices]
    check.expect(
        len(identifiers) == len(set(identifiers)),
        "structure", "every practice identifier is unique",
        "objective 3 of THREAT reads '3 Management Activities' with no full stop, so "
        "its eleven practices joined objective 2 and six identifiers existed twice",
    )
    letters = defaultdict(list)
    for practice in practices:
        letters[practice.parent_uid].append(practice.identifier[-1])
    gaps = [
        uid for uid, seq in letters.items()
        if seq != list(string.ascii_lowercase[: len(seq)])
    ]
    check.expect(
        not gaps and bool(letters),
        "structure", "practice letters run a, b, c with no gaps in all %d objectives"
        % len(letters),
        "gaps: %s" % ", ".join(gaps[:3]),
    )
    numbers = defaultdict(set)
    for objective in objectives:
        numbers[objective.parent_uid].add(int(objective.identifier.rsplit("-", 1)[1]))
    unnumbered = [
        uid for uid, nums in numbers.items() if nums != set(range(1, max(nums) + 1))
    ]
    check.expect(
        not unnumbered and bool(numbers),
        "structure", "objectives are numbered 1..n in every domain",
    )
    check.expect(
        all(c.parent_uid for c in practices) and all(c.parent_uid for c in objectives),
        "structure", "every practice sits under an objective and every objective under "
        "a domain",
    )
    check.expect(
        all(c.identifier.startswith(c.section_ref.split()[0]) for c in practices),
        "structure", "a practice identifier names its own domain",
        "the document refers to its practices as ARCHITECTURE-1f in running text, and "
        "these are the document's own identifiers rather than generated ones",
    )

    # -- the maturity indicator level, which is the obligation ---------------

    missing = [c.identifier for c in practices if not c.tag_list("maturity_indicator_level")]
    check.expect(
        not missing,
        "level", "every practice carries a maturity indicator level",
        "the marker sits in the left margin below the practice it opens, and on some "
        "pages shares a baseline with it; missing it lost RISK-4a to RISK-4c entirely "
        "and left RISK-4d and RISK-4e with no level at all (%s)" % ", ".join(missing[:4]),
    )
    bad_level = [
        c.identifier for c in practices
        if c.tag_list("maturity_indicator_level")
        and c.tag_list("maturity_indicator_level")[0] not in LEVELS
    ]
    check.expect(not bad_level, "level", "every level is MIL1, MIL2 or MIL3")
    unsorted_objectives = []
    for objective in objectives:
        seq = [
            int(c.tag_list("maturity_indicator_level")[0][-1])
            for c in practices
            if c.parent_uid == objective.uid and c.tag_list("maturity_indicator_level")
        ]
        if seq != sorted(seq):
            unsorted_objectives.append(objective.identifier)
    check.expect(
        not unsorted_objectives,
        "level", "levels never go backwards inside an objective",
        "the document orders practices by level, so a band boundary in the wrong place "
        "shows up here: %s" % ", ".join(unsorted_objectives[:3]),
    )
    sample = corpus.control("c2m2:asset-1a")
    check.expect(
        sample is not None
        and dict(currency_of(sample)).get("C2M2 maturity indicator level") == "MIL1",
        "level", "the level is reported as C2M2's own currency, under its own name",
        "reported as an obligation strength it would read as weaker than the SOCI Act's "
        "'mandatory', and C2M2 does not use that vocabulary at all",
    )

    # -- what the Rules do with it -------------------------------------------

    incorporating = [
        l for l in corpus.links
        if l.target_uid.startswith("c2m2") and l.kind is LinkKind.INCORPORATES
    ]
    by_provision = {}
    for link in incorporating:
        by_provision.setdefault(link.source_uid, set()).add(link.basis)
    check.expect(
        set(by_provision) == {"cirmp-rules:s 8.4", "cirmp-rules:s 8a.3"},
        "rules", "both CIRMP framework tables incorporate C2M2 (%s)"
        % ", ".join(sorted(by_provision)),
        "C2M2 loaded after the legislation produced no links at all and nothing said so, "
        "because tier 1 resolves its tables against frameworks already in the corpus",
    )
    conditions = {
        uid: " ".join(bases) for uid, bases in by_provision.items()
    }
    check.expect(
        "Maturity Indicator Level 1" in conditions.get("cirmp-rules:s 8.4", "")
        and "Maturity Indicator Level 2" in conditions.get("cirmp-rules:s 8a.3", ""),
        "rules", "the general regime requires MIL1 and the enhanced regime MIL2",
        "both links read 'named in the framework table of this provision', so the two "
        "regimes were indistinguishable in every chain",
    )
    check.expect(
        all(l.provenance is Provenance.PUBLISHED for l in incorporating)
        and all(l.asserted_by for l in incorporating),
        "rules", "every one of those links is published and names its asserter",
    )

    # -- licence --------------------------------------------------------------

    framework = corpus.frameworks["c2m2"]
    check.expect(
        framework.licence is Licence.SHIPPABLE and bool(framework.attribution),
        "licence", "C2M2 ships with an acknowledgement",
        "the NOTICE page grants reproduction and display and authorises others to do "
        "the same; the grant is the reason it ships and the acknowledgement is part of it",
    )
    check.expect(
        "Carnegie Mellon" in (framework.attribution or ""),
        "licence", "the acknowledgement names the copyright holder, not the publisher",
        "DOE releases and maintains it; the copyright is Carnegie Mellon University's",
    )

    # -- reachable ------------------------------------------------------------

    check.expect(
        named_set("C2M2") is not None and named_set("C2M2")[0] == "c2m2",
        "search", "naming the document returns the document",
        "a maturity model's rows describe stages and rarely name the model, so a query "
        "that is the document's name is not a word search",
    )
    index = SearchIndex(corpus)
    result = index.search("asset inventory", limit=40)
    check.expect(
        any(h.control.framework_key == "c2m2" for h in result.hits),
        "search", "a topical query reaches C2M2 practices",
        "loading a framework nothing can retrieve is the same as not loading it",
    )

    # -- what is deliberately not stored --------------------------------------

    crossing = [
        l for l in corpus.links
        if {l.source_uid.split(":")[0], l.target_uid.split(":")[0]} == {"c2m2", "aescsf"}
    ]
    check.expect(
        not crossing,
        "restraint", "nothing links C2M2 to the AESCSF",
        "they share every domain abbreviation because the AESCSF was built on this "
        "model, and neither publisher states a practice-level mapping here, so a link "
        "would be this tool's judgement wearing AEMO's name",
    )

    print("\nc2m2: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
