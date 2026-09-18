"""One analysis payload. Renderers consume it; none of them recompute it.

Everything here states what was found. Whether a gap matters, which of two numbers binds
a particular entity, and what to write in a finding are the reader's calls, and the tool
would have to know things it does not know to make them.

Three things this layer refuses to do.

It does not put obligation strength on one scale. Roughly a third of the corpus uses
RFC 2119 words; the rest says something else entirely — the ISM states a classification
applicability, 800-53B states a baseline, CIS states an implementation group, the AESCSF
states a maturity indicator level. Rendering the ISM as 'unknown' beside the SOCI Act's
'mandatory' would read as the ISM being weaker, when the ISM simply does not speak that
language. Each publisher's own currency is reported under its own name.

It does not call a disagreement a conflict. Twelve hours and seventy-two hours are
different deadlines and both can be met at once. A conflict is a floor above a ceiling —
two requirements that cannot both be satisfied — and that test is applied rather than
assumed.

It does not omit an empty band. A tier with nothing in it is drawn and labelled, because
position in a diagram is an assertion and a missing row reads as a question never asked.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .model import (
    Control,
    Corpus,
    Framework,
    ObligationStrength,
    Provenance,
    Tier,
    order_controls_governance_first,
    tier_bands,
)
from .terms import concepts_for
from . import framework_families as families
from .thresholds import (
    AT_LEAST,
    AT_MOST,
    Comparison,
    Threshold,
    compare,
    stated_by,
)

# What each publisher states instead of, or beside, an RFC 2119 keyword. Read off the
# loaded corpus, not assumed: these are the tag names the loaders actually store.
PUBLISHER_CURRENCY: Dict[str, List[Tuple[str, str]]] = {
    "ism": [
        ("applicability", "classifications this control applies to"),
        ("essential_eight_maturity", "Essential Eight maturity level"),
    ],
    "nist-800-53": [("sp800_53b_baseline", "SP 800-53B baseline")],
    "cis-controls": [("implementation_groups", "CIS implementation group")],
    "aescsf": [
        ("maturity_indicator_level", "AESCSF maturity indicator level"),
        ("security_profile", "AESCSF security profile"),
    ],
    "c2m2": [("maturity_indicator_level", "C2M2 maturity indicator level")],
    "pspf": [("applicability", "applies to")],
}


@dataclass
class ObligationReading:
    """What one publisher states about how binding this control is, in its own terms."""

    control: Control
    framework: Framework
    strength: ObligationStrength
    strength_provenance: Provenance
    currency: List[Tuple[str, str]] = field(default_factory=list)

    @property
    def states_a_keyword(self) -> bool:
        return (
            self.strength is not ObligationStrength.UNKNOWN
            and self.strength_provenance is Provenance.PUBLISHED
        )

    @property
    def summary(self) -> str:
        if self.states_a_keyword:
            return self.strength.value
        if self.currency:
            return "; ".join("%s: %s" % (label, value) for label, value in self.currency)
        if self.strength is not ObligationStrength.UNKNOWN:
            return "%s (read from the wording by this tool)" % self.strength.value
        return "this publisher states no strength for this control"


@dataclass
class FrameworkCoverage:
    """What one framework says on the subject, and how much of it is being shown.

    `controls` is what a screen draws; `total` is how many the analysis actually read.
    They differ because the two answer different questions, and rendering the analysis
    set put thirty SOCI provisions on screen — definitions among them — when the reader
    wanted the few that matter.
    """

    framework: Framework
    controls: List[Control] = field(default_factory=list)
    total: int = 0
    evidence: str = ""
    # Why this framework is not in the build, if it is not. Empty and absent are two
    # different answers and a reader acts on them differently: one says the publisher
    # requires nothing here, the other says nobody has looked.
    absent: str = ""

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    @property
    def hidden(self) -> int:
        return max(0, self.total - len(self.controls))


@dataclass
class TierBand:
    tier: Tier
    coverage: List[FrameworkCoverage] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return all(c.is_empty for c in self.coverage)

    @property
    def frameworks_with_something(self) -> List[FrameworkCoverage]:
        return [c for c in self.coverage if not c.is_empty]


@dataclass
class Disagreement:
    """Two publishers stating different numbers on one subject."""

    dimension: str
    left: Threshold
    right: Threshold

    @property
    def bounds_are_incompatible(self) -> bool:
        """Whether the two bounds cannot both be met — if they govern the same thing.

        A floor above a ceiling cannot be satisfied. Two ceilings can: meeting the
        tighter one meets the looser, so treating every difference as a clash would
        manufacture findings.

        The conditional is not hedging, it is the limit of what the tool knows. Matching
        on subject reaches topic level and no further, and within one topic two numbers
        often govern different duties: the ISM sets a one-month notice period for a
        service provider ceasing a service, the WA CSP gives a service provider 24 hours
        to report an incident. Those bounds are arithmetically incompatible and nothing
        is in conflict. So this is reported with both clauses attached and the reader
        decides; the tool never asserts a conflict on its own.
        """
        if self.left.canonical is None or self.right.canonical is None:
            return False
        if self.left.classifies or self.right.classifies:
            return False
        floors = [t for t in (self.left, self.right) if t.bound is AT_LEAST]
        ceilings = [t for t in (self.left, self.right) if t.bound is AT_MOST]
        if not floors or not ceilings:
            return False
        return max(t.canonical for t in floors) > min(t.canonical for t in ceilings)

    def describe(self, corpus: Corpus) -> str:
        def side(t: Threshold) -> str:
            control = corpus.control(t.control_uid)
            if control is None:
                # A renderer must not fall over on a uid it cannot resolve.
                return "%s: %s — %s" % (t.control_uid or "unknown control",
                                        t.describe(), t.subject[:110])
            name = corpus.frameworks[control.framework_key].short_name
            # The governed clause is carried through so the reader can see that two
            # deadlines on one subject are often two duties, owed by different entities
            # to different recipients, rather than a dispute about one number.
            return "%s %s: %s — %s" % (
                name, control.identifier, t.describe(), t.subject[:110]
            )

        verdict = (
            "these bounds cannot both be met if they govern the same requirement — read "
            "both clauses before calling it a conflict"
            if self.bounds_are_incompatible
            else "both can be satisfied by meeting the stricter one"
        )
        return "%s\n     %s\n     %s" % (side(self.left), side(self.right), verdict)


@dataclass
class Analysis:
    subject: str
    bands: List[TierBand]
    readings: List[ObligationReading]
    comparisons: List[Comparison]
    disagreements: List[Disagreement]
    notes: List[str] = field(default_factory=list)
    off_subject: List[Threshold] = field(default_factory=list)
    depth: int = 0
    corpus_frameworks: Dict[str, Framework] = field(default_factory=dict)
    lookup_note: str = ""

    @property
    def incompatible_bounds(self) -> List[Disagreement]:
        """Pairs worth a person reading. Not a list of conflicts; the tool cannot tell."""
        return [d for d in self.disagreements if d.bounds_are_incompatible]

    @property
    def controls(self) -> List[Control]:
        out: List[Control] = []
        for band in self.bands:
            for coverage in band.coverage:
                out.extend(coverage.controls)
        return out

    @property
    def attributions(self) -> List[Tuple[str, str]]:
        """Acknowledgements the publishers of this content require, as they wrote them.

        The OAG's guides ship because their copyright page grants reproduction in whole
        or in part provided the source is acknowledged. Shipping the text without the
        acknowledgement is the same breach as shipping it with no grant, so every
        renderer carries this and the packaging test fails if a shippable framework
        states an attribution that no renderer emits.
        """
        out: List[Tuple[str, str]] = []
        seen = set()
        for control in self.controls:
            framework = self.corpus_frameworks.get(control.framework_key)
            if framework is None or not framework.attribution:
                continue
            if framework.key in seen:
                continue
            seen.add(framework.key)
            out.append((framework.short_name, framework.attribution))
        return out

    @property
    def frameworks_silent(self) -> List[Framework]:
        """Frameworks that are in this build and say nothing on this subject.

        Absent ones are not silent and are reported separately. A shipped package holds
        nine of the eighteen, and listing the SOCI Act under 'says nothing on this
        subject' for a multi-factor query is a wrong answer, not a missing one.
        """
        return [
            coverage.framework
            for band in self.bands
            for coverage in band.coverage
            if coverage.is_empty and not coverage.absent
        ]

    @property
    def frameworks_absent(self) -> List[Tuple[Framework, str]]:
        """Registered frameworks whose source is not in this build, and why."""
        out: List[Tuple[Framework, str]] = []
        seen = set()
        for band in self.bands:
            for coverage in band.coverage:
                if coverage.absent and coverage.framework.key not in seen:
                    seen.add(coverage.framework.key)
                    out.append((coverage.framework, coverage.absent))
        return out

    @property
    def frameworks_present(self) -> int:
        """How many registered frameworks this build actually holds."""
        keys = {
            coverage.framework.key
            for band in self.bands
            for coverage in band.coverage
            if not coverage.absent
        }
        return families.count(keys)

    @property
    def strengths_are_commensurable(self) -> bool:
        """Whether every control in this payload states a strength in the same currency."""
        return all(r.states_a_keyword for r in self.readings) or not self.readings


def currency_of(control: Control) -> List[Tuple[str, str]]:
    """The tiering this publisher states for this control, in the publisher's words."""
    out: List[Tuple[str, str]] = []
    for name, label in PUBLISHER_CURRENCY.get(control.framework_key, []):
        if name == "applicability":
            value = control.applicability_text()
        else:
            value = ", ".join(control.tag_list(name))
        if value:
            out.append((label, value))
    return out


def reading_for(corpus: Corpus, control: Control) -> ObligationReading:
    return ObligationReading(
        control=control,
        framework=corpus.frameworks[control.framework_key],
        strength=control.obligation,
        strength_provenance=control.obligation_provenance,
        currency=currency_of(control),
    )


def analyse(
    corpus: Corpus,
    subject: str,
    controls: Sequence[Control],
    evidence: str = "subject search",
    display: Optional[Sequence[Control]] = None,
) -> Analysis:
    """Build the payload from a subject and the controls already gathered for it.

    The controls come from the caller — a search, a lineage, a saved set — because how
    they were found changes what the reader should make of them, and this layer refuses
    to invent that provenance for itself.

    `display` is the subset a screen should draw. Coverage counts, thresholds and
    disagreements are computed over the whole set either way, because the numbers live in
    controls that rank too deep to show.
    """
    found: Dict[str, List[Control]] = {}
    for control in controls:
        found.setdefault(control.framework_key, []).append(control)
    shown: Dict[str, List[Control]] = {}
    for control in (display if display is not None else controls):
        shown.setdefault(control.framework_key, []).append(control)

    bands: List[TierBand] = []
    for tier, frameworks in tier_bands(corpus):
        band = TierBand(tier=tier)
        for framework in frameworks:
            in_band = order_controls_governance_first(
                corpus, shown.get(framework.key, [])
            )
            band.coverage.append(
                FrameworkCoverage(
                    framework=framework,
                    controls=in_band,
                    total=len(found.get(framework.key, [])),
                    evidence=evidence if in_band else "",
                    absent=corpus.absent_frameworks.get(framework.key, ""),
                )
            )
        bands.append(band)

    readings = [reading_for(corpus, c) for c in controls]

    # A number is only comparable within a subject. Widening the control set to reach the
    # ISM patching windows, which rank around 110 for their own topic, also pulls in
    # session timeouts and key lifetimes measured in the same units. So a threshold joins
    # the comparison only when the clause it governs is about what the subject is about,
    # judged by the same concept vocabulary the search used.
    wanted = {c.key for c in concepts_for(subject)}
    thresholds: List[Threshold] = []
    off_subject: List[Threshold] = []
    for control in controls:
        for threshold in stated_by(control):
            if not wanted or wanted & {c.key for c in concepts_for(threshold.subject)}:
                thresholds.append(threshold)
            else:
                off_subject.append(threshold)
    comparisons = compare(thresholds)
    disagreements = _disagreements(thresholds)

    notes: List[str] = []
    if readings and not all(r.states_a_keyword for r in readings):
        # Three groups, not two. Lumping them produced a note saying the SOCI Act states
        # a baseline or an implementation group, which it does not — the tool had simply
        # read 'informative' off the wording of those particular provisions.
        stated = sorted({r.framework.short_name for r in readings if r.states_a_keyword})
        currency = sorted({
            r.framework.short_name
            for r in readings
            if not r.states_a_keyword and r.currency
        })
        inferred = sorted({
            r.framework.short_name
            for r in readings
            if not r.states_a_keyword and not r.currency
        })
        parts = []
        if stated:
            parts.append("%s state it as a keyword in the control text" % ", ".join(stated))
        if currency:
            parts.append(
                "%s state a classification, baseline, implementation group or maturity "
                "level instead, reported here under its own name" % ", ".join(currency)
            )
        if inferred:
            parts.append(
                "for %s the strength shown was read off the wording by this tool, not "
                "stated by the publisher" % ", ".join(inferred)
            )
        notes.append(
            "Obligation strength is not one scale here. %s. The absence of a keyword is "
            "not weakness." % "; ".join(parts)
        )
    empty_bands = [band.tier.label for band in bands if band.is_empty]
    if empty_bands:
        notes.append(
            "Nothing was found at %s. The band is shown empty rather than omitted."
            % ", ".join(empty_bands)
        )
    if thresholds and not any(c.thresholds for c in comparisons):
        notes.append(
            "Numbers appear in this set but none could be compared, because each states "
            "a quantity without saying whether it is a maximum or a minimum."
        )

    if off_subject:
        notes.append(
            "%d further quantities appear in these controls but govern something else — "
            "a session timeout, a key lifetime — and are listed rather than compared."
            % len(off_subject)
        )

    return Analysis(
        subject=subject,
        bands=bands,
        readings=readings,
        comparisons=comparisons,
        disagreements=disagreements,
        notes=notes,
        off_subject=off_subject,
        depth=len(controls),
        corpus_frameworks=dict(corpus.frameworks),
    )


def _disagreements(thresholds: Sequence[Threshold]) -> List[Disagreement]:
    """Pairs stating different numbers, within one dimension and across frameworks."""
    out: List[Disagreement] = []
    usable = [
        t for t in thresholds
        if t.canonical is not None
        and t.bound in (AT_MOST, AT_LEAST)
        and not t.classifies
    ]
    for i, left in enumerate(usable):
        for right in usable[i + 1 :]:
            if left.dimension != right.dimension:
                continue
            if families.family(left.control_uid.split(":", 1)[0]) == families.family(right.control_uid.split(":", 1)[0]):
                # One document stating two numbers is usually two cases, not a dispute.
                continue
            if left.bound == right.bound and abs(left.canonical - right.canonical) < 1e-9:
                continue
            out.append(Disagreement(dimension=left.dimension, left=left, right=right))
    return out


def gather(corpus: Corpus, index, subject: str, depth: int = 200) -> List[Control]:
    """The control set an analysis should run over, which is not the set a screen shows.

    A results screen answers 'what should I read first' and twenty-five entries is
    generous for that. Coverage and threshold comparison answer 'what does everybody say',
    and the numbers live in long, specific controls that rank mid-list: the ISM's
    Essential Eight patching windows sit around position 110 for their own topic, so a
    payload built from the visible page reported that nobody states a patching timeframe.

    A fixed window over a growing corpus narrows without saying so. At 150 the patching
    topic reported 10 stated quantities; adding an eighteenth framework, whose practices
    took 16 of those 150 places, was enough to drop 7 of them. Measured across 150, 180,
    200, 250 and 300, the count is 10, 17, 17, 17, 17 and the cost is 0.12s to 0.16s, so
    200 sits past the knee with room for the corpus to grow again.
    """
    result = index.search(subject, limit=depth, compose=False)
    return [hit.control for hit in result.hits]
