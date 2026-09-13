"""Hierarchy and cross-framework links. Every case names the defect it came from.

The chain-walking cases matter most. A chain of individually true statements can add up
to a false one, and the three rules that stop it — no sibling hops, no re-entering a
document, arrival only by a stated link — were each written after the walker produced a
wrong answer on this corpus.
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.build import build  # noqa: E402
from wacc.model import LinkKind, Provenance  # noqa: E402
from wacc.relate import SUBJECT_FLOOR, Relations  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402


class Check:
    def __init__(self) -> None:
        self.failed = 0
        self.corrected = 0

    def plan_wrong(self, area, detail, why=""):
        """A criterion that turned out to ask the wrong question.

        Recorded as failed and left exactly as written, with the measure it needed
        printed beside it. Moving the criterion would hide that the tool's answer to the
        original question changed.
        """
        self.failed += 1
        self.corrected += 1
        print("  PLAN WRONG  %-11s %s" % (area, detail))
        if why:
            print("        why: %s" % why)

    def ok(self, area, detail):
        print("  pass  %-11s %s" % (area, detail))

    def bad(self, area, detail, why=""):
        self.failed += 1
        print("  FAIL  %-11s %s" % (area, detail))
        if why:
            print("        from: %s" % why)

    def expect(self, condition, area, detail, why=""):
        if condition:
            self.ok(area, detail)
        else:
            self.bad(area, detail, why)


def run() -> int:
    corpus, _ = build(verbose=False)
    rel = Relations(corpus)
    index = SearchIndex(corpus)
    check = Check()

    # -- hierarchy ---------------------------------------------------------

    placement = rel.placement("wa-csp:1.5a")
    check.expect(
        placement is not None and placement.needs_its_parent,
        "hierarchy", "WA CSP 1.5a is marked as needing its parent to be quotable",
        "on its own it reads 'the WA Government Data Offshoring Position and Guidance', "
        "which is a document name, not a requirement",
    )
    check.expect(
        placement is not None and placement.quotable.startswith("Each entity must"),
        "hierarchy", "the quotable text carries the parent's stem",
    )
    check.expect(
        placement is not None and placement.breadcrumb == ["1", "1.5", "1.5a"],
        "hierarchy", "breadcrumb runs root first",
    )

    fragments = [
        c for c in corpus.controls.values()
        if c.parent_uid and (c.text or "")[:1].islower()
    ]
    repaired = [c for c in fragments if rel.stem_parts(c.uid)]
    check.expect(
        len(repaired) == len(fragments),
        "hierarchy",
        "all %d controls whose text begins lower-case get their parent stem"
        % len(fragments),
        "a lower-case opening is the tell that a control is a continuation",
    )

    # A cycle must be survived, not looped on. The corpus has none; the guard is the
    # point, because a loader bug is what would introduce one.
    deep = max(corpus.controls.values(), key=lambda c: c.depth)
    check.expect(
        len(rel.ancestors(deep.uid)) == deep.depth,
        "hierarchy", "ancestor count matches stored depth at the deepest control",
    )

    # -- link direction ----------------------------------------------------

    relations = rel.relations("ism:ism-1173")
    aemo = [r for r in relations if r.other.framework_key == "aescsf"]
    check.expect(
        bool(aemo) and all(not r.outward for r in aemo)
        and all(r.asserted_by == "AEMO" for r in aemo),
        "direction",
        "standing on the ISM, the AESCSF mapping is still AEMO's assertion",
        "reporting it as 'the ISM is linked to the AESCSF' attributes AEMO's judgement "
        "to ASD",
    )

    # -- empty bands say which kind of nothing -----------------------------

    pspf = rel.lineage("pspf:req 101")
    check.expect(
        pspf is not None and pspf.published.is_empty
        and "at all" in pspf.published.note,
        "empty band",
        "PSPF, which no publisher maps, says so rather than showing a blank",
        "an empty panel otherwise reads as 'nothing else requires this'",
    )
    ism = rel.lineage("wa-csp:1.5a")
    check.expect(
        ism is not None and ism.published.is_empty
        and "not in them" in ism.published.note,
        "empty band",
        "WA CSP, which is mapped elsewhere, says this control is not in the mappings",
    )
    check.expect(
        pspf is not None and len(pspf.bands) == 3,
        "empty band", "all three provenance bands are always present",
        "position in a diagram is an assertion, so an omitted band reads as a question "
        "never asked",
    )

    # -- provenance is never mixed or widened ------------------------------

    for uid in ("ism:ism-1683", "csf:id.im-1", "cis-controls:6.4"):
        lineage = rel.lineage(uid)
        mixed = [
            band for band in lineage.bands
            if any(r.provenance is not band.provenance for r in band.relations)
        ]
        check.expect(
            not mixed, "provenance", "%s bands hold one provenance each" % uid
        )

    published = [
        r for r in rel.relations("csf:id.im-1")
        if r.provenance is Provenance.PUBLISHED
    ]
    check.expect(
        all(r.asserted_by for r in published),
        "provenance", "every published link names the publisher asserting it",
    )

    # -- a framework table's condition is the obligation --------------------

    # s 8(4) names the AESCSF at Security Profile 1 and s 8A(3) names it at Security
    # Profile 2. The link recorded only "named in the framework table of this provision",
    # so a reader following either chain saw the two provisions requiring the same thing.
    # For a maturity framework the profile is the requirement.
    table_links = [
        l for l in corpus.links
        if l.source_uid.startswith("cirmp-rules") and l.kind is LinkKind.INCORPORATES
    ]
    by_source = {}
    for link in table_links:
        by_source.setdefault(link.source_uid, set()).add(link.basis)
    # C2M2 is the document both tables name: s 8(4) at MIL1 and s 8A(3) at MIL2. The
    # AESCSF was the witness until the two editions were separated, and only s 8A(3)
    # names the one the corpus holds.
    c2m2_bases = {
        l.source_uid: l.basis for l in table_links if l.target_uid.startswith("c2m2")
    }
    check.expect(
        len(c2m2_bases) == 2 and len(set(c2m2_bases.values())) == 2,
        "condition", "the two provisions naming C2M2 state different conditions",
        "both read 'named in the framework table of this provision', so Maturity "
        "Indicator Level 1 and Level 2 were indistinguishable in the output",
    )
    check.expect(
        all("Maturity Indicator Level" in b for b in c2m2_bases.values()),
        "condition", "each C2M2 link carries the level the table states",
        "the condition column is in the corpus on the provision and was dropped on "
        "the way to the link, which is what a chain reads",
    )
    aescsf_bases = {
        l.source_uid: l.basis for l in table_links if l.target_uid.startswith("aescsf")
    }
    check.expect(
        list(aescsf_bases) == ["cirmp-rules:s 8a.3"]
        and "Security Profile 2" in aescsf_bases["cirmp-rules:s 8a.3"],
        "condition", "only the enhanced regime names the AESCSF edition the corpus holds",
        "s 8(4) names the 2020-21 Framework Core and s 8A(3) names the 2023 one. One "
        "entry matching the phrase they share put the one workbook inside both "
        "obligations, and an incorporation link is the only kind that carries a duty",
    )
    check.expect(
        bool(table_links) and all(l.asserted_by for l in table_links),
        "condition", "%d framework-table links name the Commonwealth as asserting them"
        % len(table_links),
    )

    # -- the Essential Eight, strategy by strategy --------------------------
    #
    # Tested by hand first, strategy by strategy, and these are what that found. Taking a
    # whole ISM section for a strategy put sixteen of the thirty-five patch links on the
    # wrong one: 'Mitigating known vulnerabilities' holds the application patching
    # controls and the operating system ones together, and the ISM tells them apart in
    # the control text rather than in the heading. 'Office productivity suites' holds the
    # macro settings beside Office hardening, which is a different strategy again.
    import re as _re

    e8_links = defaultdict(lambda: defaultdict(set))
    for link in corpus.links:
        if not link.source_uid.startswith("cis-controls:"):
            continue
        if not link.target_uid.startswith("ism:"):
            continue
        if "Essential Eight strategy" not in (link.basis or ""):
            continue
        name = link.basis.split("strategy ", 1)[1].split(" (")[0].strip("'\"")
        e8_links[name][link.provenance].add(link.target_uid)

    check.expect(
        len(e8_links) == 8,
        "essential 8", "all eight strategies reach the ISM (%d)" % len(e8_links),
        "CIS names eight in its mapping workbook and a strategy that reaches nothing is "
        "a hole in the crosswalk at the level a WA entity is actually assessed against",
    )

    def _reached(name):
        return {u for targets in e8_links[name].values() for u in targets}

    ABOUT_OS = _re.compile(r"\boperating system", _re.I)
    ABOUT_APP = _re.compile(
        r"\bapplications\b|office productivity|web browser|\bdrivers\b|firmware"
        r"|online services", _re.I
    )
    strays = {}
    for name, wrong, right in (
        ("Patch Applications", ABOUT_OS, ABOUT_APP),
        ("Patch OS Systems", ABOUT_APP, ABOUT_OS),
    ):
        reached = _reached(name)
        strays[name] = [
            corpus.control(u).identifier for u in reached
            if wrong.search(corpus.control(u).text or "")
            and not right.search(corpus.control(u).text or "")
        ]
        check.expect(
            bool(reached) and not strays[name],
            "essential 8", "%s reaches %d ISM controls and none is the other strategy's"
            % (name, len(reached)),
            "the two patch strategies each carried the other's controls: %s"
            % ", ".join(strays[name][:4]),
        )
    macros = _reached("Configure MS Office Macros")
    check.expect(
        bool(macros)
        and all("macro" in (corpus.control(u).text or "").lower() for u in macros),
        "essential 8", "every control under Configure MS Office Macros is about macros "
        "(%d)" % len(macros),
        "Office hardening — OLE, child processes, code injection — sits in the same ISM "
        "section and belongs to User Application Hardening",
    )

    published_tag = {
        name for name, by_prov in e8_links.items() if Provenance.PUBLISHED_TAG in by_prov
    }
    check.expect(
        published_tag == {
            "Application Control", "Multi-factor Authentication",
            "User Application Hardening",
        },
        "essential 8", "three strategy names match an ISM heading word for word (%s)"
        % ", ".join(sorted(published_tag)),
        "a published-tag link is two publishers' own labels meeting; calling the other "
        "five that would be the most flattering error available here",
    )
    check.expect(
        all(
            Provenance.PUBLISHED not in by_prov for by_prov in e8_links.values()
        ),
        "essential 8", "no Essential Eight link claims to be published",
        "ASD publishes no strategy-to-ISM-control mapping at all, so a published link "
        "would be this tool's reading wearing ASD's name",
    )

    stale = [
        c.uid for c in corpus.controls.values()
        if c.tag_list("essential_eight_strategy")
    ]
    check.expect(
        not stale,
        "essential 8", "nothing is tagged with a strategy it does not have",
        "the AESCSF workbook's 'Essential Eight:' field holds the maturity level of the "
        "ISM control it cites — its only values are 'ML2, ML3', 'ML3' and 'N/A' — and "
        "stored as essential_eight_strategy it read as a strategy called ML3: %s"
        % ", ".join(stale[:3]),
    )
    cited = {
        value
        for c in corpus.controls.values()
        for value in c.tag_list("cited_ism_essential_eight_maturity")
    }
    check.expect(
        bool(cited) and all(v.replace(",", " ").split()[0].startswith("ML") for v in cited),
        "essential 8", "the cited maturity levels are maturity levels (%s)"
        % ", ".join(sorted(cited)),
    )

    # -- chain rules -------------------------------------------------------

    chains = rel.chains_to("ism:ism-1163")
    to_rules = [c for c in chains if c.end.framework_key == "cirmp-rules"]
    check.expect(
        bool(to_rules),
        "chain", "ISM-1163 reaches the CIRMP Rules through the AESCSF hierarchy",
        "walking links alone stops at the AESCSF domain, because the Rules name domains "
        "and AEMO maps practices",
    )
    reached = {c.end.identifier for c in to_rules}
    if len(reached) >= 2:
        check.ok("chain", "both CIRMP framework tables are reported, not just the first")
    else:
        check.plan_wrong(
            "chain",
            "ISM-1163 reaches %s and nothing else" % ", ".join(sorted(reached)),
            "the criterion is 'both CIRMP framework tables are reported' and it is left "
            "as written. It no longer holds from this witness, and the reason is a "
            "correction rather than a defect: s 8(4) names the 2020-21 AESCSF Framework "
            "Core, the corpus holds the 2023 one, so the ISM's AESCSF mapping reaches "
            "the enhanced regime only",
        )
        # The corrected measure, which tests what the criterion was written to protect:
        # the walker must not collapse two provisions naming one document into one chain.
        both = {
            c.end.identifier
            for c in rel.chains_to("c2m2:asset-1a", include_derived=True)
            if c.end.framework_key == "cirmp-rules"
        }
        check.expect(
            len(both) >= 2,
            "chain", "a document both tables name reports both provisions (%s)"
            % ", ".join(sorted(both)),
            "chain de-duplication kept one chain per framework and hid the enhanced "
            "regime, which is what the criterion above was written for",
        )

    def reenters(chain):
        frameworks = [chain.start.framework_key] + [h.to.framework_key for h in chain.hops]
        left = []
        for a, b in zip(frameworks, frameworks[1:]):
            if a != b:
                left.append(a)
                if b in left:
                    return True
        return False

    def has_sibling_hop(chain):
        up = False
        for hop in chain.hops:
            if hop.structural == "sits under":
                up = True
            elif hop.structural == "contains" and up:
                return True
        return False

    sweep = []
    for uid in list(corpus.controls)[:800]:
        sweep.extend(rel.chains_to(uid))

    # Derived links included, because the ISM and the AESCSF are linked in both
    # directions and that pair is where re-entry appears. Checking the first chain of
    # one control and stopping was a sample of one: with the guard removed this sweep
    # reports hundreds of re-entering chains and that single chain reports none.
    wide = []
    for uid in list(corpus.controls)[:1400]:
        wide.extend(rel.chains_to(uid, include_derived=True))
    offenders = [c for c in wide if reenters(c)]
    check.expect(
        not offenders, "chain", "no chain re-enters a document it has left",
        "ISM-1683 reached the AESCSF via CIS 6.3 and back into ISM-1504, which is a "
        "different ISM control and asserts nothing about the first",
    )
    check.expect(
        len(wide) > 500, "chain",
        "the re-entry sweep read %d chains, derived links included" % len(wide),
        "one chain is a sample, not a sweep, and the one that was checked never "
        "re-entered whatever the code did",
    )
    check.expect(
        not any(has_sibling_hop(c) for c in sweep),
        "chain", "no chain climbs to a parent and comes back down to a sibling",
        "CIS 6.4 climbed to control 6 and returned to safeguard 6.1, then used 6.1's "
        "mapping, which is what requires a sibling",
    )
    check.expect(
        all(c.hops[-1].relation is not None for c in sweep),
        "chain", "a chain arrives by a stated link, never by the document's own shelving",
        "a chain that had reached CIRMP s 8(4) climbed to s 8 and reported that as a "
        "second answer",
    )
    check.expect(
        bool(sweep), "chain", "the sweep found %d chains to check" % len(sweep),
        "a rule check that runs on an empty list has tested nothing",
    )

    # -- obligation is not connection --------------------------------------

    wa = rel.chains_to("wa-csp:1.1")
    check.expect(
        bool(wa) and not any(c.carries_obligation for c in wa),
        "obligation",
        "a WA CSP requirement reaching the CIRMP Rules carries no obligation",
        "the WA CSP states its own alignment with CSF 2.0 and the Rules name CSF 2.0; "
        "composing the two concluded that a Commonwealth instrument binds a WA agency",
    )
    check.expect(
        any("about itself" in c.caveat(corpus) for c in wa),
        "obligation", "the alignment claim is named in the caveat",
    )
    bearing = [c for c in to_rules if c.carries_obligation]
    check.expect(
        bool(bearing)
        and all(c.obligation_point.framework_key == "aescsf" for c in bearing),
        "obligation",
        "the duty attaches at the incorporated document, not at the far end",
        "CIRMP s 8(4) makes the AESCSF binding; AEMO then cross-references the ISM, and "
        "reporting a duty to implement the ISM control overstates it",
    )
    incorporating = [ln for ln in corpus.links if ln.kind is LinkKind.INCORPORATES]
    check.expect(
        bool(incorporating)
        and all(ln.provenance is Provenance.PUBLISHED for ln in incorporating),
        "obligation", "every incorporation link is published",
    )

    # -- subject neighbours ------------------------------------------------

    neighbours = rel.subject_neighbours("pspf:req 101", index)
    linked = {r.other.uid for r in rel.relations("pspf:req 101")}
    check.expect(
        bool(neighbours), "neighbours", "an unmapped PSPF requirement still has an answer"
    )
    check.expect(
        all(h.control.framework_key != "pspf" for h in neighbours),
        "neighbours", "neighbours never come from the control's own framework",
    )
    check.expect(
        all(h.control.uid not in linked for h in neighbours),
        "neighbours", "neighbours never repeat a control already linked",
    )
    check.expect(
        all(h.score >= SUBJECT_FLOOR for h in neighbours),
        "neighbours", "neighbours respect their own floor of %.2f" % SUBJECT_FLOOR,
        "at the search floor a WA CSP clause about data offshoring was offered eight "
        "neighbours scoring 0.13, none about anything it was about",
    )
    check.expect(
        [h.score for h in neighbours] == sorted((h.score for h in neighbours), reverse=True),
        "neighbours", "neighbours read in score order, not governance order",
        "the results screen surveys frameworks in governance order, which is the right "
        "answer to a typed question and the wrong one here",
    )
    check.expect(
        rel.subject_neighbours("wa-csp:1.5a", index) == [],
        "neighbours", "a control nothing resembles gets no neighbours rather than weak ones",
    )

    # -- round trip --------------------------------------------------------

    both_ways = 0
    for link in corpus.links:
        from_source = [
            r for r in rel.relations(link.source_uid)
            if r.other.uid == link.target_uid and r.link is link
        ]
        from_target = [
            r for r in rel.relations(link.target_uid)
            if r.other.uid == link.source_uid and r.link is link
        ]
        if len(from_source) == 1 and len(from_target) == 1:
            both_ways += 1
    check.expect(
        both_ways == len(corpus.links),
        "round trip",
        "all %d links read back exactly once from each end" % len(corpus.links),
        "the reverse index is built here, and a link seen twice from one side would "
        "double-count a framework in every lineage panel",
    )

    real = check.failed - check.corrected
    print("\nrelate: %d failed (%d of those are plan corrections)"
          % (check.failed, check.corrected))
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(run())
