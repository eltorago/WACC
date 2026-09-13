"""Hierarchy within a framework, and links between them.

Two questions live here and they are not the same question. Where does this control sit
in its own document, and what else requires the same thing somewhere else.

The second one has an answer for 950 of the 4,871 controls in this corpus. Six
frameworks carry no published cross-framework mapping at all — the SOCI Act, the
Premier's Circular, the PSPF, the OAG guides, the ASD Active Directory guidance and
every NIST specification. An empty lineage panel therefore has two meanings and this
module never lets them blur: nobody has published a mapping, or a mapping exists and
this control is not in it. Position in a diagram is an assertion, so an empty band is
drawn, labelled and explained rather than left out.

Nothing here computes a transitive link. A published A to B and a published B to C do
not make A to C published, or derived, or anything at all. Two-hop connections are
returned as paths with both hops and both publishers visible, and they never enter the
bands.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence, Set, Tuple

from .model import (
    Control,
    Corpus,
    Link,
    LinkKind,
    Mitigation,
    Provenance,
    Technique,
    order_controls_governance_first,
)
from .terms import concepts_in, content_stems

# How far a subject search reaches when a control has no published mapping, and how many
# of its results are worth offering. Both are small on purpose: this is an alternative to
# an empty panel, not a second search screen.
SUBJECT_NEIGHBOURS = 8

# Higher than the search floor on purpose. The bar for 'this matched what you typed' is
# not the bar for 'this is the same requirement somewhere else', and at the search floor
# a WA CSP clause about data offshoring was offered eight neighbours scoring 0.13, none
# of which were about anything it was about.
SUBJECT_FLOOR = 0.35

# How many chains to keep per framework reached. One was not enough: two provisions of
# the CIRMP Rules name framework tables, and only the first was ever shown.
PER_FRAMEWORK = 3

# A control reaches the threat layer only by this tool matching on subject, so the bar is
# higher than for a search result and the reading is labelled derived wherever it appears.
MITIGATION_FLOOR = 0.45
WEIGHT_NAME = 0.65
WEIGHT_BODY = 0.20
# A shared concept is the vocabulary layer stating that two texts are about one
# subject, which is stronger evidence than words happening to coincide. Weighted
# below incidental overlap, it left ISM-0843 'Application control is implemented on
# workstations' unmatched to Execution Prevention, whose description says application
# control in as many words.
WEIGHT_SHARED_CONCEPT = 0.45
MITIGATION_LIMIT = 3
# A clear best match should not be diluted by weaker ones. ISM-1683 matches
# Multi-factor Authentication exactly; keeping two 0.5 matches beside it took the
# techniques reached from 48 to 138 without adding anything true.
MITIGATION_BAND = 0.75


@dataclass
class Relation:
    """One link, read from the side the person is standing on."""

    link: Link
    other: Control
    outward: bool

    @property
    def provenance(self) -> Provenance:
        return self.link.provenance

    @property
    def asserted_by(self) -> Optional[str]:
        return self.link.asserted_by

    @property
    def basis(self) -> str:
        return self.link.basis

    def direction_note(self, corpus: Corpus) -> str:
        """Who is pointing at whom, and therefore whose assertion this is.

        It matters which end you start from. AEMO maps an AESCSF practice to an ISM
        control; standing on the ISM control, the mapping is still AEMO's and says
        nothing about what ASD thinks. Reporting it as 'the ISM is linked to the AESCSF'
        quietly attributes AEMO's judgement to ASD.
        """
        other_name = corpus.frameworks[self.other.framework_key].short_name
        if self.link.provenance is Provenance.DERIVED:
            return "matched to %s on subject by this tool" % other_name
        if self.link.provenance is Provenance.PUBLISHED_TAG:
            return self.link.tag_side or (
                "both ends carry a publisher tag; which side was inferred is not recorded"
            )
        who = self.link.asserted_by or "the publisher"
        if self.outward:
            return "%s states this link, in the %s document" % (
                who,
                corpus.frameworks[self.link.source_uid.split(":", 1)[0]].short_name,
            )
        return "%s states this link, in %s" % (who, other_name)


@dataclass
class Band:
    provenance: Provenance
    relations: List[Relation] = field(default_factory=list)
    note: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.relations

    @property
    def is_citable(self) -> bool:
        return self.provenance.is_citable


@dataclass
class Lineage:
    control: Control
    published: Band
    published_tag: Band
    derived: Band

    @property
    def bands(self) -> List[Band]:
        """Every band, including the empty ones, strongest evidence first."""
        return [self.published, self.published_tag, self.derived]

    @property
    def frameworks_reached(self) -> List[str]:
        out: List[str] = []
        for band in self.bands:
            for relation in band.relations:
                if relation.other.framework_key not in out:
                    out.append(relation.other.framework_key)
        return out

    @property
    def has_anything(self) -> bool:
        return any(not band.is_empty for band in self.bands)


@dataclass
class Hop:
    """One step of a chain. Either a stated link, or a document's own structure.

    A parent-child step is published by definition — it is how the publisher laid the
    document out — but it is a different kind of evidence from a mapping, so it is
    labelled separately and never silently counted as one.
    """

    frm: Control
    to: Control
    relation: Optional[Relation] = None
    structural: Optional[str] = None

    @property
    def provenance(self) -> Provenance:
        if self.relation is not None:
            return self.relation.provenance
        return Provenance.PUBLISHED

    def describe(self, corpus: Corpus) -> str:
        if self.relation is not None:
            return "%s to %s — %s" % (
                self.frm.identifier,
                self.to.identifier,
                self.relation.direction_note(corpus),
            )
        return "%s to %s — %s within %s" % (
            self.frm.identifier,
            self.to.identifier,
            self.structural or "structure",
            corpus.frameworks[self.to.framework_key].short_name,
        )


@dataclass
class Path:
    """A multi-step connection, kept as its steps.

    Collapsing this into a link would invent an assertion nobody made. It is shown as
    what it is: the CIRMP Rules name the AESCSF THREAT domain, the AESCSF places practice
    THREAT-1a in that domain, and AEMO maps THREAT-1a to ISM-1163. Three publishers, three
    statements, no fourth statement that the Rules require ISM-1163.
    """

    hops: List[Hop]

    @property
    def strength(self) -> Provenance:
        """A chain is only as strong as its weakest step."""
        order = [Provenance.PUBLISHED, Provenance.PUBLISHED_TAG, Provenance.DERIVED]
        return max((h.provenance for h in self.hops), key=order.index)

    @property
    def is_all_published(self) -> bool:
        return self.strength is Provenance.PUBLISHED

    @property
    def start(self) -> Control:
        return self.hops[0].frm

    @property
    def end(self) -> Control:
        return self.hops[-1].to

    @property
    def kinds(self) -> List[LinkKind]:
        return [h.relation.link.kind for h in self.hops if h.relation is not None]

    @property
    def obligation_point(self) -> Optional[Control]:
        """The last document this chain reaches that something actually requires.

        Beyond that point the chain is publishers cross-referencing each other, which is
        how you read a requirement, not what the requirement is. CIRMP s 8(4) makes the
        AESCSF binding; AEMO then says ISM-1163 covers the same ground as RISK-2a. The
        duty attaches to the AESCSF practice, and reporting it as a duty to implement
        ISM-1163 overstates the obligation.
        """
        point = None
        for hop in self.hops:
            if hop.relation is None:
                continue
            if hop.relation.link.kind is LinkKind.ALIGNS_WITH:
                return None
            if hop.relation.link.kind is LinkKind.INCORPORATES:
                point = hop.to if hop.relation.outward else hop.frm
        return point

    @property
    def carries_obligation(self) -> bool:
        return self.obligation_point is not None

    def caveat(self, corpus: Corpus) -> str:
        """What this chain establishes, in the words it can actually support."""
        if any(k is LinkKind.ALIGNS_WITH for k in self.kinds):
            return (
                "one step is a document describing its own alignment with another. "
                "That is a claim the document makes about itself and it carries no "
                "requirement along the chain."
            )
        point = self.obligation_point
        if point is None:
            return (
                "every step is a publisher cross-referencing another document. The "
                "chain shows that these controls are read as covering the same ground, "
                "not that either requires the other."
            )
        instrument = corpus.frameworks[point.framework_key].short_name
        return (
            "the requirement attaches at %s %s. Beyond that the chain is publishers "
            "cross-referencing each other." % (instrument, point.identifier)
        )

    def describe(self, corpus: Corpus) -> str:
        return "; then ".join(hop.describe(corpus) for hop in self.hops)


@dataclass
class Placement:
    """Where a control sits in its own document."""

    control: Control
    ancestors: List[Control]
    children: List[Control]
    siblings: List[Control]
    quotable: str
    stem_parts: List[Control]

    @property
    def breadcrumb(self) -> List[str]:
        return [c.identifier for c in self.ancestors] + [self.control.identifier]

    @property
    def needs_its_parent(self) -> bool:
        """Whether quoting this control alone would misrepresent it."""
        return bool(self.stem_parts)


class Relations:
    """Both indexes, built once.

    The corpus stores a link in one direction. Every question a crosswalk asks is
    symmetric, so the reverse index is built here rather than scanning 2,165 links for
    every control the interface draws.
    """

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self._out: Dict[str, List[Link]] = {}
        self._in: Dict[str, List[Link]] = {}
        self._children: Dict[str, List[Control]] = {}
        self._build()

    def _build(self) -> None:
        for link in self.corpus.links:
            self._out.setdefault(link.source_uid, []).append(link)
            self._in.setdefault(link.target_uid, []).append(link)
        for control in self.corpus.controls.values():
            if control.parent_uid:
                self._children.setdefault(control.parent_uid, []).append(control)
        for group in self._children.values():
            group.sort(key=lambda c: c.identifier_key)

    # -- hierarchy ---------------------------------------------------------

    def ancestors(self, uid: str) -> List[Control]:
        """Root first. Stops on a missing or repeated parent rather than looping."""
        out: List[Control] = []
        seen: Set[str] = {uid}
        control = self.corpus.control(uid)
        while control is not None and control.parent_uid:
            if control.parent_uid in seen:
                break
            seen.add(control.parent_uid)
            parent = self.corpus.control(control.parent_uid)
            if parent is None:
                break
            out.append(parent)
            control = parent
        out.reverse()
        return out

    def children(self, uid: str) -> List[Control]:
        return list(self._children.get(uid, []))

    def descendants(self, uid: str) -> Iterator[Control]:
        for child in self.children(uid):
            yield child
            for deeper in self.descendants(child.uid):
                yield deeper

    def siblings(self, uid: str) -> List[Control]:
        control = self.corpus.control(uid)
        if control is None or not control.parent_uid:
            return []
        return [c for c in self.children(control.parent_uid) if c.uid != uid]

    def stem_parts(self, uid: str) -> List[Control]:
        """The ancestors a quotation of this control cannot leave out.

        WA CSP 1.5a is 'the WA Government Data Offshoring Position and Guidance'. On its
        own that is a document name, not a requirement; its parent supplies 'Each entity
        must define and understand its risks associated with data ...'. Seventy-four
        controls in this corpus read as fragments this way and forty-six of them begin
        with a lower-case letter, which is the tell.
        """
        control = self.corpus.control(uid)
        if control is None:
            return []
        parts: List[Control] = []
        current = control
        while current.parent_uid:
            parent = self.corpus.control(current.parent_uid)
            if parent is None:
                break
            own = (current.text or "").strip()
            parent_text = (parent.text or "").strip()
            continues = own[:1].islower() or parent_text.endswith((":", ";"))
            if not continues:
                break
            parts.append(parent)
            current = parent
        parts.reverse()
        return parts

    def quotable_text(self, uid: str) -> str:
        """The control as it has to be quoted for the quotation to be true."""
        control = self.corpus.control(uid)
        if control is None:
            return ""
        own = (control.text or "").strip()
        parts = self.stem_parts(uid)
        if not parts:
            return own
        stems = [(p.text or "").strip() for p in parts if (p.text or "").strip()]
        return " ".join(stems + [own])

    def placement(self, uid: str) -> Optional[Placement]:
        control = self.corpus.control(uid)
        if control is None:
            return None
        return Placement(
            control=control,
            ancestors=self.ancestors(uid),
            children=self.children(uid),
            siblings=self.siblings(uid),
            quotable=self.quotable_text(uid),
            stem_parts=self.stem_parts(uid),
        )

    # -- links -------------------------------------------------------------

    def relations(self, uid: str) -> List[Relation]:
        """Every stored link touching this control, read from its side."""
        out: List[Relation] = []
        for link in self._out.get(uid, []):
            other = self.corpus.control(link.target_uid)
            if other is not None:
                out.append(Relation(link=link, other=other, outward=True))
        for link in self._in.get(uid, []):
            other = self.corpus.control(link.source_uid)
            if other is not None:
                out.append(Relation(link=link, other=other, outward=False))
        return out

    def lineage(self, uid: str) -> Optional[Lineage]:
        control = self.corpus.control(uid)
        if control is None:
            return None
        found = self.relations(uid)
        bands = {}
        for provenance in (
            Provenance.PUBLISHED,
            Provenance.PUBLISHED_TAG,
            Provenance.DERIVED,
        ):
            group = [r for r in found if r.provenance is provenance]
            group = self._order(group)
            bands[provenance] = Band(
                provenance=provenance,
                relations=group,
                note=self._band_note(control, provenance, group),
            )
        return Lineage(
            control=control,
            published=bands[Provenance.PUBLISHED],
            published_tag=bands[Provenance.PUBLISHED_TAG],
            derived=bands[Provenance.DERIVED],
        )

    def _order(self, relations: Sequence[Relation]) -> List[Relation]:
        by_uid = {r.other.uid: r for r in relations}
        ordered = order_controls_governance_first(
            self.corpus, [r.other for r in relations]
        )
        return [by_uid[c.uid] for c in ordered]

    def _band_note(
        self, control: Control, provenance: Provenance, group: Sequence[Relation]
    ) -> str:
        if group:
            return ""
        framework = self.corpus.frameworks.get(control.framework_key)
        name = framework.short_name if framework else control.framework_key
        if provenance is Provenance.DERIVED:
            return "this tool has matched nothing to this control on subject"
        mapped = self.framework_is_mapped(control.framework_key)
        label = (
            "published mappings" if provenance is Provenance.PUBLISHED
            else "published-tag matches"
        )
        if not mapped:
            return (
                "no publisher states a cross-framework mapping for %s at all, so this "
                "is an absence of %s rather than evidence that nothing else requires "
                "this" % (name, label)
            )
        return (
            "%s carries %s elsewhere, and this control is not in them" % (name, label)
        )

    def framework_is_mapped(self, framework_key: str) -> bool:
        """Whether any control in this framework is touched by a stored link."""
        return any(
            uid.split(":", 1)[0] == framework_key
            for uid in list(self._out) + list(self._in)
        )

    # -- two-hop, kept as hops ---------------------------------------------

    def _steps(
        self,
        control: Control,
        include_derived: bool,
        visited_frameworks: Set[str],
        ascended: bool,
        descended: bool,
    ) -> List[Tuple[Hop, bool, bool]]:
        """Every legitimate move from one control, with the two rules that make a chain
        mean something.

        A chain never re-enters a document it has already left. Without that rule,
        ISM-1683 reached the AESCSF by way of CIS 6.3 and back into ISM-1504, which is a
        different ISM control and asserts nothing about the first.

        A chain never descends after it has ascended. Without that rule, CIS 6.4 climbed
        to its parent control 6 and came back down to safeguard 6.1, then used 6.1's
        mapping — which is what requires a sibling, not what requires 6.4.
        """
        out: List[Tuple[Hop, bool, bool]] = []
        for relation in self.relations(control.uid):
            if not include_derived and relation.provenance is Provenance.DERIVED:
                continue
            if relation.other.framework_key in visited_frameworks:
                continue
            out.append(
                (Hop(frm=control, to=relation.other, relation=relation), ascended, descended)
            )
        if control.parent_uid and not descended:
            parent = self.corpus.control(control.parent_uid)
            if parent is not None:
                out.append(
                    (Hop(frm=control, to=parent, structural="sits under"), True, descended)
                )
        if not ascended:
            for child in self.children(control.uid):
                out.append(
                    (Hop(frm=control, to=child, structural="contains"), ascended, True)
                )
        return out

    def chains_to(
        self,
        uid: str,
        max_steps: int = 4,
        include_derived: bool = False,
        limit: int = 12,
    ) -> List[Path]:
        """Which more governing documents this control connects to, and how.

        Connection, not obligation. The chain is a sequence of statements by different
        publishers, and whether any of them requires anything is read off the chain's
        own caveat, not from the fact that a statute sits at the end of it.

        This is the question the tool exists to answer, and one link never answers it.
        The CIRMP Rules name an AESCSF domain, not a practice; the practices sit two
        levels below that domain, and it is a practice that AEMO maps to the ISM. Walking
        links alone stops at the domain and reports that no statute reaches the ISM,
        which is false.

        Breadth-first, so the shortest chain to each framework wins, and a framework is
        only reported once. Chains never merge into a link and each carries its own
        weakest-step strength.
        """
        start = self.corpus.control(uid)
        if start is None:
            return []
        start_rank = self._governance_rank(start.framework_key)
        if start_rank is None:
            return []

        found: Dict[str, List[Path]] = {}
        seen: Set[str] = {uid}
        # (control, chain, frameworks already left, ascended, descended)
        frontier: List[Tuple[Control, List[Hop], Set[str], bool, bool]] = [
            (start, [], set(), False, False)
        ]

        for _ in range(max_steps):
            following: List[Tuple[Control, List[Hop], Set[str], bool, bool]] = []
            for control, hops, left, ascended, descended in frontier:
                for hop, now_up, now_down in self._steps(
                    control, include_derived, left, ascended, descended
                ):
                    if hop.to.uid in seen:
                        continue
                    seen.add(hop.to.uid)
                    chain = hops + [hop]
                    onward = set(left)
                    if hop.to.framework_key != control.framework_key:
                        onward.add(control.framework_key)
                    rank = self._governance_rank(hop.to.framework_key)
                    # A chain arrives at a document because somebody stated a link into
                    # it, never because of that document's own shelving. Without this,
                    # a chain that had already reached CIRMP s 8(4) climbed one more
                    # level to s 8 and reported that as a second, longer answer.
                    arrived = (
                        rank is not None
                        and rank < start_rank
                        and hop.relation is not None
                    )
                    if arrived:
                        # Several provisions of one instrument can reach the same
                        # control. The CIRMP Rules carry two framework tables, and
                        # keeping only the first chain per framework hid the enhanced
                        # regime in s 8A(3) behind s 8(4).
                        reached = found.setdefault(hop.to.framework_key, [])
                        if len(reached) < PER_FRAMEWORK:
                            reached.append(Path(hops=chain))
                    following.append((hop.to, chain, onward, now_up, now_down))
            frontier = following
            if sum(len(g) for g in found.values()) >= limit or not frontier:
                break

        flat = [path for group in found.values() for path in group]
        return sorted(
            flat,
            key=lambda p: (
                self._governance_rank(p.end.framework_key) or 99,
                len(p.hops),
                p.end.identifier_key,
            ),
        )[:limit]

    def _governance_rank(self, framework_key: str) -> Optional[int]:
        framework = self.corpus.frameworks.get(framework_key)
        if framework is None or framework.tier is None:
            return None
        return framework.tier.value

    def paths(self, uid: str, max_hops: int = 2, published_only: bool = True) -> List[Path]:
        """Two-step connections between documents, never collapsed into a link."""
        start = self.corpus.control(uid)
        if start is None or max_hops < 2:
            return []
        out: List[Path] = []
        for first in self.relations(uid):
            if published_only and first.provenance is not Provenance.PUBLISHED:
                continue
            for second in self.relations(first.other.uid):
                if published_only and second.provenance is not Provenance.PUBLISHED:
                    continue
                if second.other.uid in (uid, first.other.uid):
                    continue
                if second.other.framework_key in (
                    start.framework_key,
                    first.other.framework_key,
                ):
                    continue
                out.append(
                    Path(hops=[
                        Hop(frm=start, to=first.other, relation=first),
                        Hop(frm=first.other, to=second.other, relation=second),
                    ])
                )
        return out

    # -- subject neighbours, always derived --------------------------------

    def subject_neighbours(self, uid: str, index, limit: int = SUBJECT_NEIGHBOURS):
        """What a subject search from this control's own words finds elsewhere.

        For four in five controls there is no published mapping to show, and an empty
        panel is a poor answer to 'what else requires this'. These are returned separately
        from the bands and are derived by construction: the tool matched them on subject
        and no publisher said anything. They are never written back into the corpus as
        links.
        """
        control = self.corpus.control(uid)
        if control is None:
            return []
        query = self.quotable_text(uid)
        if control.title and not control.title_is_shared:
            query = "%s %s" % (control.title, query)
        already = {r.other.uid for r in self.relations(uid)}
        # compose=False: the results screen surveys frameworks in governance order, which
        # is the right answer to a typed question and the wrong one here. This panel asks
        # which controls are closest to this one, so it reads in score order.
        result = index.search(
            query, limit=limit + len(already) + 24, compose=False
        )
        out = []
        for hit in result.hits:
            if hit.score < SUBJECT_FLOOR:
                break
            if hit.control.uid == uid or hit.control.uid in already:
                continue
            if hit.control.framework_key == control.framework_key:
                continue
            out.append(hit)
            if len(out) >= limit:
                break
        return out


@dataclass
class ThreatReading:
    """What a control looks like from the threat side, and how weak that reading is.

    Two steps, and they are not equally sound. This tool matches a control to a MITRE
    mitigation on subject, which is derived and nothing more. MITRE then states which
    techniques that mitigation blunts, which is published. The chain is only as strong as
    its first step, so every technique reached this way is derived, and none of it is
    coverage: a mitigation is MITRE explaining what blunts an attack, not a requirement
    anyone is obliged to meet.
    """

    control: Control
    mitigations: List[Tuple[Mitigation, float]] = field(default_factory=list)
    techniques: List[Technique] = field(default_factory=list)
    note: str = ""

    @property
    def by_tactic(self) -> List[Tuple[str, List[Technique]]]:
        """Techniques grouped by what stage of an attack they belong to.

        A hundred technique identifiers in a row says nothing a reader can use. The
        tactics say where in an attack this control bites, which is the shape of the
        answer an exposure statement needs.
        """
        groups: Dict[str, List[Technique]] = {}
        for technique in self.techniques:
            for tactic in technique.tactics or ["unstated"]:
                groups.setdefault(tactic, []).append(technique)
        return sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))

    @property
    def strength(self) -> Provenance:
        return Provenance.DERIVED

    @property
    def is_empty(self) -> bool:
        return not self.mitigations


def _covered(needles: Sequence[str], haystack: Sequence[str], weight_of) -> float:
    """Share of the needles' weight that the haystack carries."""
    wanted = set(needles)
    if not wanted:
        return 0.0
    total = sum(weight_of(stem) for stem in wanted) or 1.0
    return sum(weight_of(stem) for stem in wanted & set(haystack)) / total


def _resemblance(control_stems, mitigation, weight_of) -> float:
    """How much a control and a MITRE mitigation are about the same thing.

    Matched on the mitigation's name, not its prose. A MITRE description runs to hundreds
    of words, so asking what share of it a five-word control covers scores every real
    match near zero, and asking the reverse scores every long description near one:
    'Privileged access events are centrally logged' came out 0.88 against User Account
    Control, a mitigation about restricting rather than logging. The name is the subject
    label — 'Multi-factor Authentication', 'Limit Software Installation' — and asking
    whether the control says what the mitigation is called is a question both texts can
    answer. The description is kept as weaker supporting evidence.
    """
    name_stems = content_stems(mitigation.name)
    body_stems = content_stems(mitigation.description)
    by_name = _covered(name_stems, control_stems, weight_of)
    by_body = _covered(control_stems, body_stems, weight_of)

    # Two texts naming the same subject in different words. The vocabulary layer already
    # knows that application control and execution prevention are one subject; without
    # this, ISM-0843 matched no mitigation at all.
    control_concepts = {c.key for c in concepts_in(" ".join(control_stems))}
    mitigation_concepts = {
        c.key for c in concepts_in("%s %s" % (mitigation.name, mitigation.description))
    }
    shared_concept = bool(control_concepts & mitigation_concepts)

    score = WEIGHT_NAME * by_name + WEIGHT_BODY * by_body
    if shared_concept:
        score += WEIGHT_SHARED_CONCEPT
    return min(1.0, score)


def threat_reading(
    corpus: Corpus, relations: "Relations", uid: str, index, limit: int = MITIGATION_LIMIT
) -> Optional[ThreatReading]:
    """Which ATT&CK mitigations this control resembles, and what they blunt.

    Matched here rather than through the control index, because the forty-four
    mitigations are not controls and must never appear in a control result set. Forty-four
    linear comparisons cost nothing and keep the two collections apart.
    """
    control = corpus.control(uid)
    if control is None:
        return None
    if not corpus.mitigations:
        return ThreatReading(
            control=control,
            note="no threat layer is loaded, so nothing is matched",
        )

    text = content_stems(
        "%s %s" % (control.title or "", relations.quotable_text(uid))
    )
    scored: List[Tuple[Mitigation, float]] = []
    for mitigation in corpus.mitigations.values():
        score = _resemblance(text, mitigation, index.weight_of)
        if score >= MITIGATION_FLOOR:
            scored.append((mitigation, round(score, 4)))
    scored.sort(key=lambda pair: (-pair[1], pair[0].key))
    if scored:
        cutoff = scored[0][1] * MITIGATION_BAND
        scored = [pair for pair in scored if pair[1] >= cutoff]
    scored = scored[:limit]

    techniques: List[Technique] = []
    seen: Set[str] = set()
    for mitigation, _ in scored:
        for technique in corpus.techniques_for(mitigation.key):
            if technique.key not in seen:
                seen.add(technique.key)
                techniques.append(technique)
    techniques.sort(key=lambda t: t.key)

    if scored:
        note = (
            "this tool matched the control to %d ATT&CK mitigation%s on subject; MITRE "
            "then states which techniques those blunt. The match is derived, so every "
            "technique here is derived too, and none of it is coverage."
            % (len(scored), "" if len(scored) == 1 else "s")
        )
    else:
        note = (
            "no ATT&CK mitigation resembles this control closely enough to offer. That "
            "is this tool finding no resemblance, not MITRE stating an absence."
        )
    return ThreatReading(
        control=control, mitigations=scored, techniques=techniques, note=note
    )
