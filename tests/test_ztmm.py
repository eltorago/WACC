"""The Zero Trust Maturity Model, which is a new shape in this corpus.

Every other framework states controls. This one states what an agency looks like at four
maturity stages, and the parser had to be built from word positions because the tables do
not survive table detection. Each case names the defect it came from; most of them are
counts, because a parser that silently loses half a document is the failure that matters.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.build import build  # noqa: E402
from wacc.model import Fidelity, Licence, Provenance, Tier  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402

STAGES = ("Traditional", "Initial", "Advanced", "Optimal")
PILLARS = {
    "Identity": 7,
    "Devices": 7,
    "Networks": 7,
    "Applications and Workloads": 8,
    "Data": 8,
    "Cross-Cutting Capabilities": 3,
}


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

    framework = corpus.frameworks.get("ztmm")
    check.expect(framework is not None, "registry", "ZTMM is a registered framework")
    if framework is None:
        return 1

    check.expect(
        framework.tier is Tier.OUTCOME,
        "registry", "ZTMM sits at tier 3 beside the CSF and the AESCSF",
        "it describes what an agency looks like at a stage rather than stating a "
        "control, which is the tier 3 shape and not a catalogue's",
    )
    check.expect(
        framework.fidelity is Fidelity.STRUCTURED_EXTRACT,
        "registry", "its fidelity says the text came out of a PDF",
    )
    check.expect(
        framework.licence is Licence.SHIPPABLE,
        "registry", "TLP:CLEAR on every page is the document stating its own terms",
        "ATT&CK is held import-only because its export states no terms anywhere; this "
        "one does, on every page",
    )

    controls = corpus.controls_for("ztmm")
    functions = [c for c in controls if not c.attributes.get("structural")]
    containers = [c for c in controls if c.attributes.get("structural")]

    check.expect(
        len(functions) == 40,
        "parser", "40 functions extracted, not %d" % len(functions),
        "pdfplumber reported nine columns where there are five and split wrapped cells "
        "across rows; reading word positions instead is the only way this is reliable",
    )
    check.expect(
        len(containers) == 6,
        "parser", "six pillar containers",
    )

    by_pillar = {}
    for control in functions:
        by_pillar[control.section_ref] = by_pillar.get(control.section_ref, 0) + 1
    check.expect(
        by_pillar == PILLARS,
        "parser", "every pillar holds the functions it should: %s"
        % ", ".join("%s %d" % (k, v) for k, v in sorted(by_pillar.items())),
        "attributing rows to a pillar by looking for a bare pillar name on its own line "
        "found one heading in the whole document and put all 226 rows under it",
    )

    # Names, which is where the parser failed in four separate ways.
    names = {c.title for c in functions}
    check.expect(
        not any("TLP" in n or "CISA resources" in n or "FIDO2" in n for n in names),
        "parser", "no footnote text is glued to a function name",
        "footnotes begin three points left of the Function column, and a six-point "
        "tolerance swallowed them into it",
    )
    check.expect(
        not any("Zero Trust Maturity Model" in n for n in names),
        "parser", "the running header is not a function",
    )
    check.expect(
        "Network Segmentation" in names and "Network Traffic Management" in names,
        "parser", "two functions whose names sit adjacent are not merged",
        "a bold line opens a row when its own cells begin 'Agency', which is how every "
        "cell in the document is written",
    )
    check.expect(
        "Automation and Orchestration Capability" in names
        and sum(1 for c in functions if c.title == "Automation and Orchestration Capability") == 5,
        "parser", "a function whose stage text starts on the next line is not lost",
        "'Automation and' with empty cells followed by 'Orchestration Capability' with "
        "the text was swallowed into the row above it",
    )
    check.expect(
        "Application Access" in names,
        "parser", "a name whose annotation wraps mid-bracket stays one function",
        "'Application Access (Formerly Access' then 'Authorization)' split in two",
    )
    check.expect(
        max(len(n) for n in names) < 60,
        "parser", "no function name has run into its neighbour (longest is %d chars)"
        % max(len(n) for n in names),
    )

    # The stages are the content, and all four are kept.
    complete = [
        c for c in functions
        if len(c.tag_list("maturity_stages")) == 4
    ]
    check.expect(
        len(complete) == len(functions),
        "stages", "every function carries all four maturity stages",
        "a stage lost in extraction is a maturity level the tool would silently not "
        "know about",
    )
    sample = corpus.control("ztmm:identity/authentication")
    check.expect(
        sample is not None and all(
            sample.publisher_tags.get("stage_%s" % s.lower(), "").startswith("Agency")
            for s in STAGES
        ),
        "stages", "each stage is stored separately and reads as the document wrote it",
    )
    check.expect(
        sample is not None and all(s in (sample.text or "") for s in STAGES),
        "stages", "the control text is the progression, not one stage chosen as the target",
        "picking Optimal as the text would assert that CISA requires it, and the model "
        "describes where an agency is rather than where it must be",
    )

    check.expect(
        all(c.obligation_provenance is Provenance.PUBLISHED for c in functions),
        "obligation", "the absence of an obligation keyword is recorded as published",
        "CISA states no strength, and that is a fact about the document rather than "
        "something this tool failed to read",
    )

    # It has to be reachable, or none of the above matters.
    index = SearchIndex(corpus)
    result = index.search("zero trust maturity", limit=25)
    check.expect(
        any(h.control.framework_key == "ztmm" for h in result.hits),
        "search", "a zero trust query reaches ZTMM",
    )
    segmentation = index.search("network segmentation", limit=25)
    check.expect(
        any(h.control.framework_key == "ztmm" for h in segmentation.hits),
        "search", "a subject query reaches ZTMM alongside the other frameworks",
    )

    check.expect(
        not corpus.links_from("ztmm:identity/authentication"),
        "links", "nothing claims a published mapping from ZTMM to anything",
        "CISA publishes no mapping to the ISM or the PSPF, so a stored link would be "
        "this tool's judgement wearing CISA's name",
    )

    print("\nztmm: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
