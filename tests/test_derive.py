"""Archetypes, derived tests and risk statements, and product detail.

Every case names the defect it came from. The ones that matter most are the refusals: a
tool that writes a test procedure for a definition, or a risk statement for a Ministerial
power, produces text nobody checked and a finding nobody can defend.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.archetypes import ARCHETYPES_BY_KEY, classify, not_derivable  # noqa: E402
from wacc.build import build  # noqa: E402
from wacc.derive import DETAIL_FLOOR, DetailIndex, derive  # noqa: E402
from wacc.model import Licence, Provenance, StatementKind, Tier  # noqa: E402
from wacc.relate import Relations  # noqa: E402
from wacc.registry import DETAIL_SOURCES  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402

# Phrases the brief bars from generated text. A tool that tells a reader what to conclude
# has written the finding for them.
BANNED = re.compile(
    r"\b(worth stating|this suggests|it is recommended|you should|we recommend|"
    r"best practice|arguably|it seems|may indicate|consider whether)\b", re.I
)


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def expect(self, condition, area, detail, why=""):
        if condition:
            print("  pass  %-12s %s" % (area, detail))
        else:
            self.failed += 1
            print("  FAIL  %-12s %s" % (area, detail))
            if why:
                print("        from: %s" % why)


def run() -> int:
    corpus, _ = build(verbose=False)
    relations = Relations(corpus)
    index = SearchIndex(corpus)
    details = DetailIndex(corpus, index.weight_of)
    check = Check()

    # -- refusals ----------------------------------------------------------

    definition = derive(corpus, corpus.control("soci-act:s 12l.1"), relations)
    check.expect(
        definition.refusal is not None and definition.refusal.reason == "definition",
        "refusal", "SOCI s 12L(1) is refused as a definition",
        "on its own text it reads as an assertion about the world and classified as an "
        "outcome, producing a risk statement that the outcome was not achieved",
    )
    check.expect(
        definition.refusal is not None and "s 12L" in definition.refusal.detail,
        "refusal", "the refusal names the nearest defining ancestor, not the outermost",
        "'Part 1 Preliminary' is true and tells a reader less than 'Meaning of "
        "responsible entity'",
    )
    check.expect(
        not definition.derived_tests and definition.risk is None,
        "refusal", "a refused control produces no test and no risk statement",
    )

    structural = [c for c in corpus.controls.values() if c.attributes.get("structural")]
    check.expect(
        bool(structural)
        and all(
            not_derivable(c, relations.ancestors(c.uid)) is not None
            for c in structural[:40]
        ),
        "refusal", "structural headings are refused",
    )

    counts = {}
    for control in corpus.controls.values():
        result = not_derivable(control, relations.ancestors(control.uid))
        if result:
            counts[result.reason] = counts.get(result.reason, 0) + 1
    check.expect(
        counts.get("power of an office holder", 0) > 40,
        "refusal", "%d provisions conferring power on an office holder are refused"
        % counts.get("power of an office holder", 0),
        "a Ministerial power is not something the audited entity implements",
    )

    # -- classification ----------------------------------------------------

    every = 0
    unshaped = 0
    fallback = 0
    for control in corpus.controls.values():
        archetypes, evidence, refusal = classify(control, relations.ancestors(control.uid))
        if refusal:
            continue
        every += 1
        if not archetypes:
            unshaped += 1
        if evidence and evidence[0].startswith("no more specific"):
            fallback += 1
    check.expect(
        unshaped == 0,
        "classify", "every derivable control gets a shape (%d controls, %d by fallback)"
        % (every, fallback),
        "classifying by sentence shape left 42 per cent in an 'other' bucket, because "
        "publishers write the same requirement in every voice",
    )
    check.expect(
        0 < fallback < every * 0.5,
        "classify", "the fallback carries %.0f%% and is flagged, not hidden"
        % (100.0 * fallback / every),
        "a default nobody can see is a classifier that has stopped classifying",
    )

    logging_control = corpus.control("ism:ism-1985")
    archetypes, _, _ = classify(logging_control, relations.ancestors(logging_control.uid))
    check.expect(
        len(archetypes) > 1,
        "classify", "a control can hold several shapes at once",
        "'Event logs are retained and reviewed' is a record and a periodic activity, and "
        "forcing one archetype loses two thirds of the test",
    )

    # -- derived text ------------------------------------------------------

    patching = derive(corpus, corpus.control("ism:ism-1690"), relations)
    check.expect(
        any("no more than 2 weeks" in t.text for t in patching.derived_tests),
        "threshold", "a test cites the figure the control states",
        "the ISM writes its Essential Eight patching windows in words, and a test that "
        "does not carry the number cannot be carried out",
    )
    check.expect(
        any("NC, OS, P, S, TS" in t.text for t in patching.derived_tests),
        "applicability", "a test carries the publisher's own applicability",
    )

    fragment = derive(corpus, corpus.control("wa-csp:1.5a"), relations)
    check.expect(
        "Each entity must define" in fragment.derived_tests[0].text,
        "quote", "a fragment is quoted with the parent stem that makes it a requirement",
        "'the WA Government Data Offshoring Position and Guidance' alone is a document "
        "name",
    )
    check.expect(
        "Guidance. Evidence:" in fragment.derived_tests[0].text,
        "quote", "the quote is terminated so it does not run into the next sentence",
    )

    for uid in ("ism:ism-1690", "soci-act:s 30bc.1", "wa-csp:1.5a", "nist-800-53:ia-2.1"):
        result = derive(corpus, corpus.control(uid), relations)
        texts = [t.text for t in result.derived_tests] + [result.risk.text]
        offenders = [t[:60] for t in texts if BANNED.search(t)]
        check.expect(
            not offenders, "plain", "%s states what was found, not what to conclude" % uid,
            "no 'worth stating in a finding', no 'this suggests'",
        )

    statute = derive(corpus, corpus.control("soci-act:s 30bc.1"), relations)
    check.expect(
        "statutory obligation" not in statute.risk.text and "Requirement:" not in statute.risk.text,
        "tier", "risk statements omit authority commentary and requirement citations",
    )
    spec = derive(corpus, corpus.control("nist-800-131a:sp 800-131a rev 2 §2#1"), relations)
    check.expect(
        spec.risk is None or "programme" not in spec.risk.text,
        "tier", "risk statements omit generic tier commentary",
        "a missing statutory provision and a missing key length are not the same kind "
        "of problem and should not read as though they were",
    )

    # -- published stays published -----------------------------------------

    nist = derive(corpus, corpus.control("nist-800-53:ia-2.1"), relations)
    check.expect(
        nist.has_published_procedure
        and all(s.provenance is Provenance.PUBLISHED for s in nist.published),
        "published", "800-53A procedures are attached as NIST's own",
    )
    check.expect(
        all(s.provenance is Provenance.DERIVED for s in nist.derived_tests),
        "published", "derived tests are never mixed into the published list",
    )
    check.expect(
        all(s.published_by for s in nist.published),
        "published", "every published procedure names its publisher",
    )

    # -- product detail ----------------------------------------------------

    expected_details = {
        str(source["key"]): int(source["expected"]) for source in DETAIL_SOURCES
    }
    detail_counts = {}
    for detail in corpus.details.values():
        detail_counts[detail.source_key] = detail_counts.get(detail.source_key, 0) + 1
    check.expect(
        bool(expected_details)
        and all(expected_details.get(key) == count for key, count in detail_counts.items()),
        "detail", "%d locally available benchmark recommendations have expected counts"
        % len(corpus.details),
        "CIS extracts are intentionally local and the application supports any complete subset",
    )
    check.expect(
        all(d.licence is Licence.IMPORT_ONLY for d in corpus.details.values()),
        "detail", "every benchmark recommendation is import-only",
    )

    browser = derive(corpus, corpus.control("ism:ism-1486"), relations, details)
    check.expect(
        set(browser.detail_sources) == {"cis-chrome", "cis-edge"},
        "detail", "a web browser control brings only the browser benchmarks into scope",
        "word overlap alone offered an Azure Bastion Host against 'Web browsers do not "
        "process Java' and a minimum password age against browser settings",
    )
    check.expect(
        all(d.source_key in ("cis-chrome", "cis-edge") for d in browser.detail),
        "detail", "no recommendation from an out-of-scope product is attached",
    )

    backup = derive(corpus, corpus.control("ism:ism-1813"), relations, details)
    check.expect(
        not backup.detail_sources and not backup.detail,
        "detail", "a backup control brings no benchmark into scope",
    )

    generic = derive(corpus, corpus.control("ism:ism-1412"), relations, details)
    check.expect(
        generic.detail_sources and not generic.detail
        and "the benchmark as a whole is the detail" in generic.derived_tests[0].text,
        "detail", "a generally worded hardening control names the benchmark, not 257 settings",
    )
    check.expect(
        "import-only" in generic.derived_tests[0].text,
        "detail", "the licence is stated wherever benchmark detail appears",
    )
    check.expect(
        all(score >= DETAIL_FLOOR for _, score in details.for_control(
            corpus.control("ism:ism-1486"), "Web browsers do not process Java from the internet.")),
        "detail", "attached recommendations clear the floor of %.2f" % DETAIL_FLOOR,
    )

    # -- nothing is stored -------------------------------------------------

    before = len(corpus.statements)
    derive(corpus, corpus.control("ism:ism-1690"), relations, details)
    derive(corpus, corpus.control("ism:ism-1690"), relations, details)
    check.expect(
        len(corpus.statements) == before,
        "regeneration", "derived text is generated on demand and never written back",
        "generated text that survives a parser fix is generated text that is now wrong",
    )

    print("\nderive: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
