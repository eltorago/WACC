"""Assemble the corpus.

Machine-readable sources first, and each published cross-framework mapping loads with
the framework it connects rather than as a later enrichment.

Loading order is not cosmetic. A published link can only be recorded once both ends
are present, so the catalogues load before the frameworks that cite them.
"""

import os
from typing import Dict, List, Optional, Tuple

from .model import Corpus, Framework, Licence, Tier
from .registry import FRAMEWORKS, GUIDANCE, FRAMEWORKS_BY_KEY
from .loaders import (
    aescsf,
    attack,
    cis,
    csf,
    detail,
    legislation,
    oag,
    oscal,
    pspf,
    spec,
    wa,
    c2m2,
    ztmm,
)

# WACC_SOURCES points to the local cache of publisher files used to build the live corpus.
# The cache is populated with ``python -m wacc sources`` and is never distributed with
# WACC. A custom folder may use the older development layout with documents and OSCAL
# catalogues in subfolders. Any framework that cannot be loaded is named as unavailable.
RAW = os.environ.get("WACC_SOURCES") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sources", "files"
)
CORPUS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "corpus"
)


def _sources(*parts: str) -> str:
    """A path under the sources folder, tolerating a flat folder as well as subfolders."""
    nested = os.path.join(RAW, *parts)
    if os.path.exists(nested) or len(parts) == 1:
        return nested
    flat = os.path.join(RAW, parts[-1])
    return flat if os.path.exists(flat) else nested


DOCUMENTS = _sources("documents")
if not os.path.isdir(DOCUMENTS):
    DOCUMENTS = RAW


def _doc(name: str) -> str:
    return os.path.join(DOCUMENTS, name)


def _exists(path: str) -> bool:
    return os.path.exists(path)


class LoadReport:
    def __init__(self) -> None:
        self.loaded: Dict[str, Dict] = {}
        self.skipped: Dict[str, str] = {}

    def record(self, key: str, counts: Dict) -> None:
        self.loaded[key] = counts

    def skip(self, key: str, reason: str) -> None:
        self.skipped[key] = reason

    def lines(self, corpus: Corpus) -> List[str]:
        out: List[str] = []
        for framework in corpus.ordered_frameworks():
            key = framework.key
            controls = len(corpus.controls_for(key))
            if key in self.skipped:
                out.append(
                    "  tier %s  %-14s  NOT LOADED — %s"
                    % (framework.tier.value if framework.tier is not None else "?", framework.short_name, self.skipped[key])
                )
                continue
            revision = framework.revision or "revision not stated"
            out.append(
                "  tier %s  %-14s  %5d controls  %-22s  %s"
                % (
                    framework.tier.value if framework.tier is not None else "?",
                    framework.short_name,
                    controls,
                    revision,
                    framework.fidelity.value,
                )
            )
        return out


def build(verbose: bool = True) -> Tuple[Corpus, LoadReport]:
    corpus = Corpus()
    report = LoadReport()

    for framework in FRAMEWORKS:
        corpus.add_framework(framework)
    for doc in GUIDANCE:
        corpus.add_guidance(doc)

    # -- tier 4 first: everything else cites these -------------------------

    ism = FRAMEWORKS_BY_KEY["ism"]
    ism_catalog = _sources("acsc-ism", "ISM_catalog.json")
    if _exists(ism_catalog):
        counts = oscal.load_into(corpus, ism, ism_catalog, applicability_prop="applicability")
        for level in ("ML1", "ML2", "ML3"):
            profile = _sources("acsc-ism", "ISM_E8_%s-baseline_profile.json" % level)
            if _exists(profile):
                counts["e8_%s" % level] = oscal.apply_profile_tag(
                    corpus, ism, profile, "essential_eight_maturity", level
                )
        report.record(ism.key, counts)
    else:
        report.skip(ism.key, "ISM_catalog.json not present")

    n53 = FRAMEWORKS_BY_KEY["nist-800-53"]
    n53_catalog = _sources("nist-800-53", "NIST_SP-800-53_rev5_catalog.json")
    if _exists(n53_catalog):
        counts = oscal.load_into(
            corpus, n53, n53_catalog, assessment_publisher="NIST SP 800-53A Rev 5.2.0"
        )
        for level in ("LOW", "MODERATE", "HIGH", "PRIVACY"):
            profile = _sources(
                "nist-800-53", "NIST_SP-800-53_rev5_%s-baseline_profile.json" % level
            )
            if _exists(profile):
                counts["baseline_%s" % level.lower()] = oscal.apply_profile_tag(
                    corpus, n53, profile, "sp800_53b_baseline", level.lower()
                )
        report.record(n53.key, counts)
    else:
        report.skip(n53.key, "800-53 OSCAL catalog not present")

    cis_controls = FRAMEWORKS_BY_KEY["cis-controls"]
    cis_path = _doc("CIS_Controls_Version_8.xlsx")
    if _exists(cis_path):
        counts = cis.load_controls(corpus, cis_controls, cis_path)
        mapping = _doc("CIS_Controls_v8.1_Mapping_to_ASD_Essential_Eight_2_2025.xlsx")
        if _exists(mapping):
            counts["e8_mapping"] = cis.load_essential_eight_mapping(
                corpus, cis_controls, mapping
            )
            counts["ism_bridge"] = cis.link_safeguards_to_ism(corpus)
        report.record(cis_controls.key, counts)
    else:
        report.skip(cis_controls.key, "CIS Controls workbook not present")

    # -- tier 3 -------------------------------------------------------------

    csf_fw = FRAMEWORKS_BY_KEY["csf"]
    csf_path = _doc("nist-csf-2.0-cprt-all-olir.xlsx")
    if _exists(csf_path):
        report.record(csf_fw.key, csf.load_into(corpus, csf_fw, csf_path))
    else:
        report.skip(csf_fw.key, "CSF CPRT export not present")

    oag_fw = FRAMEWORKS_BY_KEY["oag-wa"]
    oag_path = os.path.join(CORPUS, "oag-wa.json")
    if _exists(oag_path):
        report.record(oag_fw.key, oag.load_into(corpus, oag_fw, oag_path))
    else:
        report.skip(oag_fw.key, "oag-wa.json not extracted yet")

    aescsf_fw = FRAMEWORKS_BY_KEY["aescsf"]
    aescsf_path = _doc("aescsf-framework-core.xlsx")
    if _exists(aescsf_path):
        report.record(aescsf_fw.key, aescsf.load_into(corpus, aescsf_fw, aescsf_path))
    else:
        report.skip(aescsf_fw.key, "AESCSF workbook not present")

    # C2M2 belongs here rather than with the other tier-3 addition below, because the
    # CIRMP framework tables name it and tier 1 resolves those tables against frameworks
    # that are already loaded. Loaded after the legislation it produced no links at all,
    # and nothing said so.
    c2m2_framework = corpus.frameworks.get("c2m2")
    c2m2_path = os.path.join(CORPUS, "c2m2.json")
    if c2m2_framework is not None:
        if os.path.exists(c2m2_path):
            report.record("c2m2", c2m2.load(corpus, c2m2_framework, c2m2_path, verbose))
        else:
            report.skip("c2m2", "extract not present; run tools/extract_c2m2.py")

    # -- tier 2 -------------------------------------------------------------

    pspf_fw = FRAMEWORKS_BY_KEY["pspf"]
    pspf_path = os.path.join(CORPUS, "pspf.json")
    if _exists(pspf_path):
        report.record(pspf_fw.key, pspf.load_into(corpus, pspf_fw, pspf_path))
    else:
        report.skip(pspf_fw.key, "pspf.json not extracted yet")

    wa_csp = FRAMEWORKS_BY_KEY["wa-csp"]
    wa_csp_path = os.path.join(CORPUS, "wa-csp.json")
    if _exists(wa_csp_path):
        report.record(wa_csp.key, wa.load_policy(corpus, wa_csp, wa_csp_path))
    else:
        report.skip(wa_csp.key, "wa-csp.json not extracted yet")

    wa_circular = FRAMEWORKS_BY_KEY["wa-circular"]
    wa_circular_path = os.path.join(CORPUS, "wa-circular.json")
    if _exists(wa_circular_path):
        report.record(wa_circular.key, wa.load_circular(corpus, wa_circular, wa_circular_path))
    else:
        report.skip(wa_circular.key, "wa-circular.json not extracted yet")

    # -- tier 5 -------------------------------------------------------------

    n63 = FRAMEWORKS_BY_KEY["nist-800-63"]
    n63_path = os.path.join(CORPUS, "nist-800-63.json")
    if _exists(n63_path):
        report.record(n63.key, spec.load_json(corpus, n63, n63_path, "volumes", "volume"))
    else:
        report.skip(n63.key, "nist-800-63.json not extracted yet")

    for key, filename in (
        ("nist-800-131a", "nist-800-131a.json"),
        ("nist-800-57pt1", "nist-800-57pt1.json"),
        ("nist-800-88", "nist-800-88.json"),
        ("asd-ad", "asd-ad.json"),
    ):
        fw = FRAMEWORKS_BY_KEY[key]
        path = os.path.join(CORPUS, filename)
        if _exists(path):
            report.record(key, spec.load_json(corpus, fw, path, "groups", "key"))
        else:
            report.skip(key, "no parameter table and no curated extract")

    # -- tier 1 last, because the frameworks its tables name must exist first

    for key, filename in (
        ("soci-act", "soci-act-latest.docx"),
        ("cirmp-rules", "cirmp-rules-latest.docx"),
    ):
        fw = FRAMEWORKS_BY_KEY[key]
        path = _doc(filename)
        if _exists(path):
            report.record(key, legislation.load_into(corpus, fw, path))
        else:
            report.skip(key, "%s not present" % filename)

    # -- tier 3 addition: a maturity model, not a catalogue ----------------

    ztmm_framework = corpus.frameworks.get("ztmm")
    ztmm_path = os.path.join(CORPUS, "ztmm.json")
    if ztmm_framework is not None:
        if os.path.exists(ztmm_path):
            report.record("ztmm", ztmm.load(corpus, ztmm_framework, ztmm_path, verbose))
        else:
            report.skip("ztmm", "extract not present; run tools/extract_ztmm.py")

    # -- product detail, which is not a framework column -------------------
    #
    # A benchmark states how to configure one product. It has no tier and never
    # appears as a column; it reaches a reader inside the test procedure for the
    # control it hardens.

    detail.load(corpus, os.path.join(CORPUS, "detail"), verbose=verbose)

    # -- threat layer, last and separate -----------------------------------
    #
    # Loaded after every framework and kept out of the tier bands entirely. ATT&CK
    # carries no authority over an entity, so placing it in the spine would assert
    # something about it that is not true.

    attack_path = _doc("enterprise-attack-v19.2.xlsx")
    if os.path.exists(attack_path):
        attack.load(corpus, attack_path, verbose=verbose)
    else:
        corpus.load_warnings.append(
            "ATT&CK export not present; the threat layer is empty"
        )

    # -- everything not yet written ----------------------------------------

    for framework in FRAMEWORKS:
        if framework.key in report.loaded or framework.key in report.skipped:
            continue
        report.skip(framework.key, "loader not written yet")

    # What is registered but not here, and why. Every consumer reads this off the corpus,
    # because the alternative is each renderer deciding for itself what an empty column
    # means, and the two meanings are not the same.
    corpus.absent_frameworks = dict(report.skipped)

    corpus.mark_shared_titles()

    if verbose:
        print("\n".join(report.lines(corpus)))
    return corpus, report


def summary(corpus: Corpus, report: LoadReport) -> str:
    from .model import Provenance

    published = sum(1 for l in corpus.links if l.provenance is Provenance.PUBLISHED)
    tagged = sum(1 for l in corpus.links if l.provenance is Provenance.PUBLISHED_TAG)
    derived = sum(1 for l in corpus.links if l.provenance is Provenance.DERIVED)
    shippable = [f for f in corpus.frameworks.values() if f.licence is Licence.SHIPPABLE]
    lines = [
        "",
        "controls          %d across %d frameworks (%d frameworks still unloaded)"
        % (len(corpus.controls), len(report.loaded), len(report.skipped)),
        "published stmts   %d" % len(corpus.statements),
        "links             %d published, %d published-tag, %d derived"
        % (published, tagged, derived),
        "licence           %d shippable, %d import-only"
        % (len(shippable), len(corpus.frameworks) - len(shippable)),
        "guidance layer    %d documents" % len(corpus.guidance),
        "product detail    %d benchmark recommendations across %d sources"
        % (len(corpus.details), len({d.source_key for d in corpus.details.values()})),
        "threat layer      %d techniques, %d mitigations, %d published mitigates "
        "edges" % (len(corpus.techniques), len(corpus.mitigations), len(corpus.mitigates)),
    ]
    empty = [
        t for t in Tier if not [f for f in corpus.frameworks_in_tier(t) if corpus.controls_for(f.key)]
    ]
    if empty:
        lines.append(
            "empty tiers       %s" % ", ".join("%d (%s)" % (t.value, t.label) for t in empty)
        )
    return "\n".join(lines)


if __name__ == "__main__":
    corpus, report = build()
    print(summary(corpus, report))
    if corpus.load_warnings:
        print("\nload warnings (%d):" % len(corpus.load_warnings))
        for w in corpus.load_warnings:
            print("  - %s" % w)
    problems = corpus.check()
    if problems:
        print("\nchecks (%d):" % len(problems))
        for p in problems[:20]:
            print("  - %s" % p)
