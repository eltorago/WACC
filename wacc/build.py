"""Assemble the corpus.

Machine-readable sources first, and each published cross-framework mapping loads with
the framework it connects rather than as a later enrichment.

Loading order is not cosmetic. A published link can only be recorded once both ends
are present, so the catalogues load before the frameworks that cite them.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .model import Corpus, Framework, Licence, Tier
from .framework_families import count as family_count
from .registry import FRAMEWORKS, GUIDANCE, FRAMEWORKS_BY_KEY
from .sources import local_path, source_directory
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
    extended,
    principles,
    wa_pris,
)

# WACC_SOURCES points to the local cache of publisher files used to build the live corpus.
# The cache is populated with ``python -m wacc sources`` and is never distributed with
# WACC. A custom folder may use the older development layout with documents and OSCAL
# catalogues in subfolders. Any framework that cannot be loaded is named as unavailable.
RAW = str(source_directory())
CORPUS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "corpus"
)


def _sources(*parts: str) -> str:
    """Use the same flat/nested-file resolution as source acquisition and status."""
    return str(local_path(Path(RAW), parts[-1]))


def _doc(name: str) -> str:
    return _sources(name)


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


def build(verbose: bool = True, *, source_root=None, corpus_root=None, framework_keys=None) -> Tuple[Corpus, LoadReport]:
    """Load all sources, or only selected frameworks and their source dependencies.

    AESCSF needs ISM to resolve its published references and maturity tags. Other
    frameworks and the product/threat layers are skipped in a selective load.
    Each build owns its metadata; source editions cannot leak between builds.
    """
    from copy import deepcopy

    selected = None if framework_keys is None else set(framework_keys)
    if selected is not None:
        unknown = selected - set(FRAMEWORKS_BY_KEY)
        if unknown:
            raise ValueError("Unknown frameworks: " + ", ".join(sorted(unknown)))
        if selected & {'aescsf', 'asd-principles'}:
            selected.add('ism')
        if 'ism' in selected:
            selected.add('asd-principles')
    source_directory = Path(source_root or RAW)
    corpus_directory = Path(corpus_root or CORPUS)
    corpus, report = Corpus(), LoadReport()
    for framework in FRAMEWORKS:
        corpus.add_framework(deepcopy(framework))
    if selected is None:
        for doc in GUIDANCE:
            corpus.add_guidance(deepcopy(doc))

    def source(name):
        return str(local_path(source_directory, name))

    def load(key, path, loader, missing, **options):
        if selected is not None and key not in selected:
            return
        if _exists(path):
            report.record(key, loader(corpus, corpus.frameworks[key], str(path), **options))
        else:
            report.skip(key, missing)

    def ism_loader(corpus, framework, path):
        counts = oscal.load_into(corpus, framework, path, applicability_prop="applicability")
        for level in ("ML1", "ML2", "ML3"):
            profile = source("ISM_E8_%s-baseline_profile.json" % level)
            if os.path.exists(profile):
                counts["e8_%s" % level] = oscal.apply_profile_tag(corpus, framework, profile, "essential_eight_maturity", level)
        partition = principles.partition(corpus, corpus.frameworks['asd-principles'])
        counts['controls'] -= partition['controls']
        report.record('asd-principles', partition)
        return counts

    def nist_loader(corpus, framework, path):
        counts = oscal.load_into(corpus, framework, path, assessment_publisher="NIST SP 800-53A Rev 5.2.0")
        for level in ("LOW", "MODERATE", "HIGH", "PRIVACY"):
            profile = source("NIST_SP-800-53_rev5_%s-baseline_profile.json" % level)
            if os.path.exists(profile):
                counts["baseline_%s" % level.lower()] = oscal.apply_profile_tag(corpus, framework, profile, "sp800_53b_baseline", level.lower())
        return counts

    def cis_loader(corpus, framework, path):
        counts = cis.load_controls(corpus, framework, path)
        mapping = source("CIS_Controls_v8.1_Mapping_to_ASD_Essential_Eight_2_2025.xlsx")
        if os.path.exists(mapping):
            counts["e8_mapping"] = cis.load_essential_eight_mapping(corpus, framework, mapping)
            counts["ism_bridge"] = cis.link_safeguards_to_ism(corpus)
        return counts

    # Load referenced catalogues before the frameworks that cite them.
    load('ism', source('ISM_catalog.json'), ism_loader, 'ISM_catalog.json not present')
    if 'ism' in report.skipped:
        report.skip('asd-principles', 'ISM_catalog.json not present; run python -m wacc sources')
    load('nist-800-53', source('NIST_SP-800-53_rev5_catalog.json'), nist_loader, '800-53 OSCAL catalog not present')
    load('cis-controls', source('CIS_Controls_Version_8.xlsx'), cis_loader, 'CIS Controls workbook not present')
    load('csf', source('nist-csf-2.0-cprt-all-olir.xlsx'), csf.load_into, 'CSF CPRT export not present')
    load('oag-wa', corpus_directory/'oag-wa.json', oag.load_into, 'oag-wa.json not extracted yet')
    load('aescsf', source('aescsf-framework-core.xlsx'), aescsf.load_into, 'AESCSF workbook not present')
    load('c2m2', corpus_directory/'c2m2.json', c2m2.load, 'extract not present; run tools/extract_c2m2.py', verbose=verbose)
    load('pspf', corpus_directory/'pspf.json', pspf.load_into, 'pspf.json not extracted yet')
    load('wa-csp', corpus_directory/'wa-csp.json', wa.load_policy, 'wa-csp.json not extracted yet')
    load('wa-circular', corpus_directory/'wa-circular.json', wa.load_circular, 'wa-circular.json not extracted yet')
    load('nist-800-63', corpus_directory/'nist-800-63.json', spec.load_json, 'nist-800-63.json not extracted yet', container='volumes', group_label='volume')
    for key in ('nist-800-131a', 'nist-800-57pt1', 'nist-800-88', 'asd-ad'):
        load(key, corpus_directory/(key + '.json'), spec.load_json, 'no parameter table and no curated extract', container='groups', group_label='key')
    for key in ('soci-act', 'cirmp-rules'):
        filename = key + '-latest.docx'
        load(key, source(filename), legislation.load_into, filename + ' not present')
    load('ztmm', corpus_directory/'ztmm.json', ztmm.load, 'extract not present; run tools/extract_ztmm.py', verbose=verbose)
    for key, loader in (('wa-pris', wa_pris.load_into), ('asd-strategies', extended.strategies),
                        ('scf', extended.scf), ('mcsb', extended.mcsb),
                        ('essential-eight', extended.essential_eight), ('scuba', extended.scuba)):
        load(key, source(corpus.frameworks[key].source_file), loader, 'Source not present; run python -m wacc sources')
    if selected is None:
        detail.load(corpus, str(corpus_directory/'detail'), verbose=verbose)
        attack_path = source('enterprise-attack-v19.2.xlsx')
        if os.path.exists(attack_path):
            attack.load(corpus, attack_path, verbose=verbose)
        else:
            corpus.load_warnings.append('ATT&CK export not present; the threat layer is empty')
    for framework in FRAMEWORKS:
        if framework.key not in report.loaded and framework.key not in report.skipped:
            report.skip(framework.key, 'Not selected' if selected is not None and framework.key not in selected else 'loader not written yet')
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
        "source records    %d across %d framework families / %d source sets (%d still unloaded)"
        % (len(corpus.controls), family_count(report.loaded), len(report.loaded), len(report.skipped)),
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
