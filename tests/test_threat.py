"""Check threat context and guidance without treating either as a requirement."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.build import build  # noqa: E402
from wacc.model import Licence, Provenance, Tier  # noqa: E402
from wacc.relate import MITIGATION_FLOOR, Relations, threat_reading  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402


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
    corpus, report = build(verbose=False)
    check = Check()

    # -- the threat layer is separate --------------------------------------

    check.expect(
        len(corpus.techniques) > 600 and len(corpus.mitigations) > 40,
        "loaded", "%d techniques and %d mitigations"
        % (len(corpus.techniques), len(corpus.mitigations)),
    )
    # Not a hard-coded total: that broke the moment a framework was legitimately added,
    # which tests nothing about ATT&CK. What matters is that every control belongs to a
    # registered framework, so nothing from the threat layer is in the spine.
    accounted = sum(len(corpus.controls_for(key)) for key in corpus.frameworks)
    check.expect(
        accounted == len(corpus.controls),
        "separate", "all %d controls belong to a registered framework" % len(corpus.controls),
        "a technique loaded as a control would be cited as an obligation in a finding",
    )
    check.expect(
        len(corpus.techniques) + len(corpus.mitigations) > 700
        and not (set(corpus.techniques) | set(corpus.mitigations)) & set(corpus.controls),
        "separate", "no technique or mitigation key collides with a control uid",
    )
    check.expect(
        not any(uid.startswith("attack:") for uid in corpus.controls),
        "separate", "no ATT&CK entry is in the control collection",
    )
    check.expect(
        all(
            f.key != "attack-enterprise"
            for tier in Tier
            for f in corpus.frameworks_in_tier(tier)
        ),
        "separate", "ATT&CK is in no tier band",
        "the spine orders documents by authority over an entity and a threat taxonomy "
        "has none, so placing it in a tier asserts something untrue",
    )

    index = SearchIndex(corpus)
    check.expect(
        index.indexed == len(corpus.controls),
        "separate", "the search index holds controls only",
        "a mitigation surfacing in a control result set reads as coverage",
    )

    # -- what MITRE states, and what it does not ---------------------------

    check.expect(
        bool(corpus.mitigates)
        and all(e.provenance is Provenance.PUBLISHED for e in corpus.mitigates),
        "published", "all %d mitigates edges are MITRE's own" % len(corpus.mitigates),
    )
    check.expect(
        all(e.asserted_by == "MITRE" for e in corpus.mitigates),
        "published", "every mitigates edge names MITRE as the publisher",
    )
    check.expect(
        not any(
            link.source_uid.startswith("attack:") or link.target_uid.startswith("attack:")
            for link in corpus.links
        ),
        "published", "no stored link joins ATT&CK to any control",
        "MITRE publishes no control-framework mapping in this export, so a stored link "
        "would be this tool's judgement wearing MITRE's name",
    )

    source = corpus.threat_sources.get("attack-enterprise")
    check.expect(
        source is not None and source.version == "19.2",
        "version", "the release is read off the file, not the data",
        "the techniques sheet's version column is the technique's own revision and its "
        "domain column is the matrix name; reading domain recorded every release as "
        "'enterprise-attack'",
    )
    check.expect(
        source is not None and source.retrieved and source.retrieved.startswith("2026"),
        "version", "the build date comes from the package properties, which state it",
    )
    check.expect(
        source is not None and source.licence is Licence.IMPORT_ONLY,
        "licence", "ATT&CK is held import-only until its terms are read from the source",
        "the workbook states no terms and this build had no egress to check MITRE's "
        "site, so shipping the text would redistribute on a licence nobody had seen",
    )

    # -- reaching the threat layer from a control --------------------------

    relations = Relations(corpus)

    reading = threat_reading(corpus, relations, "ism:ism-1683", index)
    check.expect(
        reading is not None
        and reading.mitigations
        and reading.mitigations[0][0].key == "M1032",
        "match", "an MFA logging control matches Multi-factor Authentication first",
    )
    check.expect(
        reading is not None and len(reading.mitigations) == 1,
        "match", "a clear best match is not diluted by weaker ones",
        "keeping two 0.5 matches beside an exact one took the techniques reached from "
        "48 to 138 without adding anything true",
    )

    logging_control = threat_reading(corpus, relations, "ism:ism-1509", index)
    matched = [m.key for m, _ in logging_control.mitigations]
    check.expect(
        "M1052" not in matched,
        "match", "a control about logging does not match User Account Control",
        "measuring only what share of a five-word control a several-hundred-word "
        "description covers scored that pair at 0.88",
    )

    allowlisting = threat_reading(corpus, relations, "ism:ism-843", index)
    check.expect(
        any(m.key == "M1038" for m, _ in allowlisting.mitigations),
        "concept", "application control reaches Execution Prevention",
        "the names share no word; the vocabulary layer is what knows they are one "
        "subject, and weighting a shared concept below incidental overlap missed it",
    )

    statute = threat_reading(corpus, relations, "soci-act:s 30bc.1", index)
    check.expect(
        statute is not None and statute.is_empty and "not MITRE stating an absence" in statute.note,
        "empty", "a notification provision matches nothing, and says whose absence it is",
    )

    check.expect(
        all(score >= MITIGATION_FLOOR for _, score in reading.mitigations),
        "floor", "every offered mitigation clears the floor of %.2f" % MITIGATION_FLOOR,
    )
    check.expect(
        reading.strength is Provenance.DERIVED,
        "provenance", "a threat reading is derived however published its second step is",
        "this tool matches the control to a mitigation and MITRE states the techniques; "
        "the chain is only as strong as its first step",
    )
    check.expect(
        "derived" in reading.note and "none of it is coverage" in reading.note,
        "provenance", "the reading says in words that it is derived and is not coverage",
    )

    tactics = reading.by_tactic
    check.expect(
        bool(tactics) and sum(len(v) for _, v in tactics) >= len(reading.techniques),
        "tactics", "techniques group by tactic rather than listing flat",
        "a hundred technique identifiers in a row says nothing a reader can use",
    )

    # -- guidance ----------------------------------------------------------

    keys = set(corpus.guidance)
    added = {
        "asd-defensible-architecture", "asd-network-segmentation", "asd-lateral-movement",
        "asd-what-to-log", "joint-lotl", "ncsc-ot-connectivity", "easm-buyers-guide",
        "asd-secure-by-design", "asd-choosing-technologies", "cisa-vulnerability-review",
    }
    check.expect(
        added <= keys, "guidance", "all ten later publications are in the guidance layer",
    )
    check.expect(
        all(
            g.reason and g.source_file and g.publisher
            for g in corpus.guidance.values()
            if g.key in added
        ),
        "guidance", "each names its publisher, its file and why it is not loaded",
        "a guidance entry without a reason is an unexplained omission",
    )
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "sources", "permissions.json"), encoding="utf-8") as handle:
        reviewed = {entry["filename"] for entry in json.load(handle)["files"]}
    unreviewed = [
        g.source_file for g in corpus.guidance.values()
        if g.source_file and g.source_file not in reviewed
    ]
    check.expect(
        not unreviewed, "guidance", "every guidance document has a permission decision",
        "unreviewed: %s" % ", ".join(unreviewed),
    )

    print("\nthreat and guidance: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
