"""Suggested assessments and risk scenarios for individual controls.

Published procedures remain attributed and separate. Derived guidance follows the
control's own topic, preserves its acceptance criteria and stated thresholds, and
asks for operational evidence and an actionable remediation record. Risk scenarios
express possible exposure and impact, never an observed finding or a risk rating.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .archetypes import Archetype, NotDerivable, classify
from .assessment import guidance, RECORD_RESULT, assessment_sources
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

@dataclass
class AssessmentMaterial:
    control: Control
    statements: List[Statement]
    connection: Provenance
    basis: str


@dataclass
class Derivation:
    """Everything this tool can say about testing one control, and what its absence means."""

    control: Control
    archetypes: List[Archetype] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    refusal: Optional[NotDerivable] = None
    published: List[Statement] = field(default_factory=list)
    related_assessments: List[AssessmentMaterial] = field(default_factory=list)
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

    _, assessment = guidance(quote, archetype.key)
    lines = [
        "Assess %s %s. Confirm applicability, in-scope systems and the assessment period with the control owner."
        % (framework.short_name, control.identifier),
        "Acceptance criteria: %s" % quote,
        "Evidence: %s" % assessment,
        RECORD_RESULT,
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
    """A concise exposure and consequence scenario, with no tier commentary."""
    framework = corpus.frameworks[control.framework_key]
    lead = archetypes[0] if archetypes else None
    quote = _quote(corpus, control, relations)

    risk, _ = guidance(quote, lead.key if lead else "outcome")
    return Statement(
        control_uid=control.uid,
        kind=StatementKind.RISK_STATEMENT,
        text=risk,
        provenance=Provenance.DERIVED,
        archetype=lead.key if lead else None,
        tier_framing=framework.tier,
    )


def related_assessments(corpus, control, relations=None):
    """Keep source procedures intact and preserve how each source was connected."""
    candidates = {}
    if relations is not None:
        for relation in relations.relations(control.uid):
            candidates[relation.other.uid] = (
                relation.provenance, relation.direction_note(corpus))
    for uid in assessment_sources(_quote(corpus, control, relations)):
        candidates.setdefault(uid, (Provenance.DERIVED,
            "Suggested connection based on the requirement; review the source scope before using these methods."))
    materials = []
    for uid, (connection, basis) in candidates.items():
        source = corpus.control(uid)
        if source is None or uid == control.uid:
            continue
        statements = [s for s in corpus.statements_for(uid, StatementKind.TEST_PROCEDURE)
                      if s.provenance is Provenance.PUBLISHED]
        if statements:
            materials.append(AssessmentMaterial(source, statements, connection, basis))
    return materials


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

    result.related_assessments = related_assessments(corpus, control, relations)
    result.derived_tests = [
        test_procedure(corpus, control, archetype, relations) for archetype in archetypes[:1]
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
