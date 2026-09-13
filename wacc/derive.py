"""Test procedures and risk statements, derived from one archetype set.

Both answer a question about the same control and they are generated from the same
classification, because a test that does not match the risk it is meant to address is
worse than no test. The archetype decides what evidence proves the control, and the same
archetype decides what its absence exposes.

Everything here states what was found. A test procedure says what to obtain and what to
compare it against; a risk statement says what is true when the control is absent. Neither
says what to conclude, whether it matters, or what to write. That is the reader's work,
and a tool that does it for them produces findings nobody checked.

Published procedures are never mixed with derived ones. NIST publishes 3,945 assessment
objectives and methods inside the 800-53 catalogue; those are NIST's and are presented as
NIST's, above anything this tool wrote. Derived text is regenerated on every call rather
than stored, because generated text that survives a parser fix is generated text that is
now wrong.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .archetypes import Archetype, NotDerivable, classify
from .registry import DETAIL_SOURCES
from .terms import concepts_in, content_stems, normalise_text
from .model import (
    Control,
    Corpus,
    Detail,
    Provenance,
    Statement,
    StatementKind,
    Tier,
)
from .thresholds import AT_LEAST, AT_MOST, Threshold, stated_by

# What an absent control means, by the authority of the document stating it. A missing
# statutory provision and a missing key length are not the same kind of problem and
# should not read as though they were.
# A benchmark recommendation reaches a control only by this tool matching on subject, so
# the bar is set where the matches stay product-appropriate: at 0.30 a Chrome setting was
# offered against a backup control. Each one is labelled with its platform, because the
# reader has to decide whether that product is in scope here.
DETAIL_FLOOR = 0.45
DETAIL_LIMIT = 6

TIER_FRAMING: Dict[Tier, str] = {
    Tier.STATUTE: "This is a statutory obligation. Absence is non-compliance with an "
                  "instrument, not a gap against good practice.",
    Tier.MANDATED_POLICY: "This is mandated for the entity by its own jurisdiction. "
                          "Absence is non-compliance with a policy the entity is bound "
                          "by, and is reportable within that policy's own arrangements.",
    Tier.OUTCOME: "This states an outcome rather than a method. Absence means the "
                  "outcome is not achieved; which control would achieve it is a "
                  "separate question.",
    Tier.CATALOGUE: "This is a control from a catalogue. Absence is a specific technical "
                    "or procedural gap, and the catalogue's own applicability decides "
                    "whether it was required here.",
    Tier.SPECIFICATION: "This is a parameter. Absence means a value in use is wrong or "
                        "unverified, not that a programme is missing.",
}


@dataclass
class Derivation:
    """Everything this tool can say about testing one control, and what its absence means."""

    control: Control
    archetypes: List[Archetype] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    refusal: Optional[NotDerivable] = None
    published: List[Statement] = field(default_factory=list)
    derived_tests: List[Statement] = field(default_factory=list)
    risk: Optional[Statement] = None
    thresholds: List[Threshold] = field(default_factory=list)
    detail: List[Detail] = field(default_factory=list)
    detail_sources: Dict[str, str] = field(default_factory=dict)

    @property
    def by_fallback(self) -> bool:
        return any(e.startswith("no more specific") for e in self.evidence)

    @property
    def has_published_procedure(self) -> bool:
        return bool(self.published)


def _quote(corpus: Corpus, control: Control, relations=None) -> str:
    """The control as it has to be quoted for the quotation to be true."""
    if relations is not None:
        text = relations.quotable_text(control.uid)
    else:
        text = " ".join((control.text or "").split())
    text = " ".join((text or "").split())
    # Terminated, because an unterminated quote runs into the sentence after it: a WA CSP
    # clause ending in a document name read as '...Offshoring Position and Guidance
    # Evidence: ...'.
    if text and text[-1] not in ".;:!?":
        text += "."
    return text


def _threshold_line(thresholds: Sequence[Threshold]) -> Optional[str]:
    """The stated numbers, as a thing to measure against rather than a note."""
    usable = [t for t in thresholds if t.bound in (AT_MOST, AT_LEAST) and not t.classifies]
    if not usable:
        return None
    parts = []
    for threshold in usable[:3]:
        parts.append(
            "%s %s %s%s"
            % (
                "no more than" if threshold.bound is AT_MOST else "no less than",
                ("%g" % threshold.value),
                threshold.unit + ("s" if threshold.value != 1 else ""),
                " between occurrences" if threshold.cadence else "",
            )
        )
    return "Measure against the stated figure: %s." % "; ".join(parts)


def _applicability_line(control: Control) -> Optional[str]:
    """Whether the publisher says this control applied here at all."""
    text = control.applicability_text()
    if text:
        return "The publisher states this applies to: %s." % text
    baseline = control.tag_list("sp800_53b_baseline")
    if baseline:
        return "In the SP 800-53B %s baseline." % ", ".join(baseline)
    groups = control.tag_list("implementation_groups")
    if groups:
        return "In CIS implementation group %s." % ", ".join(groups)
    maturity = control.tag_list("essential_eight_maturity")
    if maturity:
        return "At Essential Eight maturity level %s." % ", ".join(maturity)
    level = control.tag_list("maturity_indicator_level")
    if level:
        return "At AESCSF %s." % ", ".join(level)
    return None


def test_procedure(
    corpus: Corpus, control: Control, archetype: Archetype, relations=None
) -> Statement:
    """One archetype's test for one control, written to be carried out."""
    framework = corpus.frameworks[control.framework_key]
    quote = _quote(corpus, control, relations)
    thresholds = stated_by(control)

    lines = [
        "%s %s %s."
        % (archetype.test_opening, framework.short_name, control.identifier),
        "It requires: %s" % quote,
        "Evidence: %s." % archetype.evidence,
    ]
    figure = _threshold_line(thresholds)
    if figure:
        lines.append(figure)
    applies = _applicability_line(control)
    if applies:
        lines.append(applies)
    if archetype.key == "prohibition":
        lines.append(
            "A statement that the condition does not occur is not evidence that it does "
            "not occur. Look for instances."
        )

    return Statement(
        control_uid=control.uid,
        kind=StatementKind.TEST_PROCEDURE,
        text=" ".join(lines),
        provenance=Provenance.DERIVED,
        archetype=archetype.key,
        tier_framing=framework.tier,
    )


def risk_statement(
    corpus: Corpus, control: Control, archetypes: Sequence[Archetype], relations=None
) -> Statement:
    """What is true if this control is absent, at the level an executive reads.

    Tier-aware, because a missing statutory provision and a missing key length are not
    the same kind of problem. Where a published chain reaches a more governing document,
    that document is named with the same caveat the chain itself carries: a chain is a
    sequence of statements by different publishers and the requirement attaches where the
    incorporation is, not at the far end.
    """
    framework = corpus.frameworks[control.framework_key]
    lead = archetypes[0] if archetypes else None
    quote = _quote(corpus, control, relations)

    lines = []
    if lead is not None:
        lines.append("%s." % lead.risk_opening)
    lines.append(
        "%s %s states: %s" % (framework.short_name, control.identifier, quote)
    )
    if framework.tier is not None:
        lines.append(TIER_FRAMING[framework.tier])

    thresholds = [
        t for t in stated_by(control)
        if t.bound in (AT_MOST, AT_LEAST) and not t.classifies
    ]
    if thresholds:
        first = thresholds[0]
        lines.append(
            "The figure stated is %s %g %s%s, so the gap is measurable rather than a "
            "matter of judgement."
            % (
                "no more than" if first.bound is AT_MOST else "no less than",
                first.value,
                first.unit + ("s" if first.value != 1 else ""),
                " between occurrences" if first.cadence else "",
            )
        )

    if relations is not None:
        chains = [c for c in relations.chains_to(control.uid) if c.carries_obligation]
        if chains:
            chain = chains[0]
            point = chain.obligation_point
            lines.append(
                "A published chain reaches %s %s. The requirement attaches at %s %s; "
                "beyond that the chain is publishers cross-referencing each other."
                % (
                    corpus.frameworks[chain.end.framework_key].short_name,
                    chain.end.identifier,
                    corpus.frameworks[point.framework_key].short_name,
                    point.identifier,
                )
            )

    return Statement(
        control_uid=control.uid,
        kind=StatementKind.RISK_STATEMENT,
        text=" ".join(lines),
        provenance=Provenance.DERIVED,
        archetype=lead.key if lead else None,
        tier_framing=framework.tier,
    )


def derive(
    corpus: Corpus, control: Control, relations=None, detail_index=None
) -> Derivation:
    """Everything this tool can say about one control, published material first."""
    ancestors = relations.ancestors(control.uid) if relations is not None else ()
    archetypes, evidence, refusal = classify(control, ancestors)
    published = corpus.statements_for(control.uid, StatementKind.TEST_PROCEDURE)
    published = [s for s in published if s.provenance is Provenance.PUBLISHED]

    result = Derivation(
        control=control,
        archetypes=archetypes,
        evidence=evidence,
        refusal=refusal,
        published=published,
        thresholds=stated_by(control),
    )
    if refusal is not None:
        return result

    result.derived_tests = [
        test_procedure(corpus, control, archetype, relations) for archetype in archetypes
    ]
    result.risk = risk_statement(corpus, control, archetypes, relations)

    if detail_index is not None:
        quote = _quote(corpus, control, relations)
        subject = "%s %s" % (control.title or "", quote)
        result.detail_sources = detail_index.sources_in_scope(subject)
        if result.detail_sources and result.derived_tests:
            # Attached to the first derived test, which is the one shaped by the control's
            # strongest evidence signal.
            result.detail = attach_detail(
                corpus, result.derived_tests[0], control, detail_index, quote
            )
            result.derived_tests[0].text += " " + _detail_line(
                corpus, result.detail_sources, result.detail
            )
    return result


def _detail_line(
    corpus: Corpus, sources: Dict[str, str], found: Sequence[Detail]
) -> str:
    """What the product benchmarks add, named so the reader can judge scope.

    A generic control — 'Web browsers are hardened using ASD and vendor hardening
    guidance' — matches no single recommendation and is covered by all of them. Naming the
    benchmark is the honest answer there; listing 257 settings is not.
    """
    from .registry import DETAIL_SOURCES

    titles = {str(s["key"]): str(s["title"]) for s in DETAIL_SOURCES}
    counts: Dict[str, int] = {}
    for detail in corpus.details.values():
        if detail.source_key in sources:
            counts[detail.source_key] = counts.get(detail.source_key, 0) + 1
    named = "; ".join(
        "%s (%d recommendations, in scope because this control says %r)"
        % (titles.get(key, key), counts.get(key, 0), phrase)
        for key, phrase in sorted(sources.items())
    )
    if found:
        settings = "; ".join("%s %s" % (d.source_key, d.identifier) for d in found[:6])
        return (
            "Product detail: %s. The closest settings are %s. These are CIS text, "
            "import-only, and whether the product is in scope here is your call." 
            % (named, settings)
        )
    return (
        "Product detail: %s. No single recommendation matches this control's wording, "
        "which is what a generally worded hardening requirement looks like against a "
        "benchmark; the benchmark as a whole is the detail. CIS text is import-only."
        % named
    )


class DetailIndex:
    """Benchmark recommendations, reachable only from a control about that product class.

    Two steps, because one does not work. Word overlap alone offered a minimum password
    age setting against 'Web browser security settings cannot be changed by human users'
    and an Azure Bastion Host against 'Web browsers do not process Java': the measure has
    no way to know that Chrome is a browser and Bastion is not.

    So a benchmark is gated on the control naming the product class the benchmark covers,
    which the registry states for each source, and only then are its recommendations
    ranked against the control's subject. 1,273 recommendations against one control is a
    linear scan that costs nothing, and keeping them out of the control search index is
    what stops a Chrome setting appearing beside an ISM control as though it were a peer.
    """

    def __init__(self, corpus: Corpus, weight_of) -> None:
        self.corpus = corpus
        self.weight_of = weight_of
        self.stems: Dict[str, List[str]] = {}
        self.concepts: Dict[str, set] = {}
        for uid, detail in corpus.details.items():
            text = "%s %s" % (detail.title, detail.text)
            self.stems[uid] = content_stems(text)
            self.concepts[uid] = {c.key for c in concepts_in(text)}
        self.covers: Dict[str, List[List[str]]] = {
            str(source["key"]): [
                normalise_text(phrase) for phrase in source.get("covers", [])
            ]
            for source in DETAIL_SOURCES
        }

    def _covered(self, needles: Sequence[str], haystack: Sequence[str]) -> float:
        wanted = set(needles)
        if not wanted:
            return 0.0
        total = sum(self.weight_of(stem) for stem in wanted) or 1.0
        return sum(self.weight_of(s) for s in wanted & set(haystack)) / total

    def sources_in_scope(self, text: str) -> Dict[str, str]:
        """Which benchmarks this control's own words bring into scope, and on what word."""
        joined = " " + " ".join(normalise_text(text)) + " "
        out: Dict[str, str] = {}
        for source in DETAIL_SOURCES:
            key = str(source["key"])
            for phrase, phrase_stems in zip(source.get("covers", []), self.covers[key]):
                if phrase_stems and " " + " ".join(phrase_stems) + " " in joined:
                    out[key] = phrase
                    break
        return out

    def for_control(
        self, control: Control, quote: str, limit: int = DETAIL_LIMIT
    ) -> List[tuple]:
        subject = "%s %s" % (control.title or "", quote)
        in_scope = self.sources_in_scope(subject)
        if not in_scope:
            return []
        control_stems = content_stems(subject)
        control_concepts = {c.key for c in concepts_in(quote)}
        scored = []
        for uid, stems in self.stems.items():
            detail = self.corpus.details[uid]
            if detail.source_key not in in_scope:
                continue
            score = self._covered(control_stems, stems)
            if control_concepts & self.concepts[uid]:
                score += 0.2
            if score >= DETAIL_FLOOR:
                scored.append((detail, round(min(1.0, score), 4)))
        scored.sort(key=lambda pair: (-pair[1], pair[0].uid))
        return scored[:limit]


def attach_detail(
    corpus: Corpus, statement: Statement, control: Control, index: DetailIndex, quote: str
) -> List[Detail]:
    """Product settings that carry out part of this control, matched on subject.

    Derived, and never presented as the control's own requirement: a benchmark says how to
    configure one product, and whether that product is in scope is the reader's call. The
    platform is carried on every one so that call can be made.
    """
    found = index.for_control(control, quote)
    statement.detail_uids = [detail.uid for detail, _ in found]
    return [detail for detail, _ in found]
