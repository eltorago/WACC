"""Shared data types for frameworks, controls, relationships and source provenance.

Each record carries its origin and extraction quality so every result can be traced back
to its source.

Python 3.9+, standard library only.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple
import re
import unicodedata


# --------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------


class Tier(int, Enum):
    """Level of authority and abstraction. Abstraction is the spine."""

    STATUTE = 1
    MANDATED_POLICY = 2
    OUTCOME = 3
    CATALOGUE = 4
    SPECIFICATION = 5

    @property
    def label(self) -> str:
        return _TIER_LABELS[self]

    @property
    def question(self) -> str:
        """What a reader is asking when they look at this band."""
        return _TIER_QUESTIONS[self]


_TIER_LABELS = {
    Tier.STATUTE: "statute",
    Tier.MANDATED_POLICY: "mandated policy",
    Tier.OUTCOME: "outcome / maturity",
    Tier.CATALOGUE: "control catalogue",
    Tier.SPECIFICATION: "technical specification",
}

_TIER_QUESTIONS = {
    Tier.STATUTE: "am I legally required to do anything",
    Tier.MANDATED_POLICY: "what has my jurisdiction told me to adopt",
    Tier.OUTCOME: "what does good look like",
    Tier.CATALOGUE: "which controls do I implement",
    Tier.SPECIFICATION: "what exactly is the number",
}


class Jurisdiction(int, Enum):
    """Attribute, not structure. The integer value is the within-tier sort rank.

    Australian material sorts before American. WA before Commonwealth, because a WA
    entity reads its own jurisdiction first.
    """

    WA = 0
    AU_COMMONWEALTH = 1
    AU_INDUSTRY = 2
    US = 3
    INTERNATIONAL = 4


class Fidelity(str, Enum):
    """How the corpus text got here. Half these corpora are transcriptions from PDFs
    and the reader is entitled to know which."""

    OFFICIAL_MACHINE_READABLE = "official machine-readable"
    STRUCTURED_EXTRACT = "structured extract"
    CURATED_EXTRACT = "curated extract"
    PUBLISHER_IMPORT = "publisher import"
    DERIVED = "derived"


class Provenance(str, Enum):
    """Where an assertion came from. Never mixed, never widened silently."""

    PUBLISHED = "published"
    PUBLISHED_TAG = "published-tag"
    DERIVED = "derived"

    @property
    def is_citable(self) -> bool:
        return self is Provenance.PUBLISHED


class LinkKind(str, Enum):
    """What one document is doing when it points at another.

    Provenance says how much to trust that the link exists. This says what the link
    means, and the two are independent. Both are needed, because composing links without
    it produces true sentences that add up to a false one: the WA CSP states that it
    aligns with CSF 2.0, and the CIRMP Rules name CSF 2.0 in a framework table, and from
    those two facts a chain-walker concluded that a Commonwealth instrument requires a
    Western Australian agency to do something. It does not.
    """

    INCORPORATES = "incorporates"
    CROSS_REFERENCE = "cross-reference"
    ALIGNS_WITH = "aligns-with"

    @property
    def carries_obligation(self) -> bool:
        """Whether crossing this link can carry a legal requirement with it.

        Only incorporation does. A cross-reference is a publisher saying two controls
        cover the same ground, which is useful and is not a duty. An alignment claim is a
        document describing itself, which binds nobody at all.
        """
        return self is LinkKind.INCORPORATES

    @property
    def description(self) -> str:
        return {
            LinkKind.INCORPORATES: "names the other document as a requirement",
            LinkKind.CROSS_REFERENCE: "points at the other document as covering the "
                                      "same ground",
            LinkKind.ALIGNS_WITH: "states that it follows the other document",
        }[self]


class Licence(str, Enum):
    SHIPPABLE = "shippable"
    IMPORT_ONLY = "import-only"


class ObligationStrength(str, Enum):
    """Strength of the obligation the control text states, not its importance."""

    MANDATORY = "mandatory"
    EXPECTED = "expected"
    RECOMMENDED = "recommended"
    DISCOURAGED = "discouraged"
    PERMITTED = "permitted"
    PROHIBITED = "prohibited"
    INFORMATIVE = "informative"
    UNKNOWN = "unknown"


class StatementKind(str, Enum):
    TEST_PROCEDURE = "test procedure"
    RISK_STATEMENT = "risk statement"


class Origin(str, Enum):
    """Which side of a corpus merge a control arrived from."""

    SHIPPED = "shipped"
    GENERATED = "generated"


# --------------------------------------------------------------------------
# Identifier normalisation
# --------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_IDENT_STRIP = re.compile(r"[\s ]+")


def normalise_identifier(raw: str) -> str:
    """Fold an identifier to a comparable form.

    Identifiers are not words. AC-6(5) ends in a parenthesis, ISM-0421 and 0421 name
    the same control, and PSPF Req 93 shares a prefix with two hundred siblings. This
    produces a key for exact lookup; it never produces a search term.
    """
    s = unicodedata.normalize("NFKD", raw or "")
    s = _IDENT_STRIP.sub(" ", s).strip().lower()
    s = s.replace("–", "-").replace("—", "-").replace("−", "-")
    # Bracket forms are interchangeable in the wild: AC-6(5), AC-6[5], AC-6.5, and
    # legislative s 8(4) against s 8.4. Dotted is the canonical stored form, so the
    # OSCAL id ac-6.5 and the printed label AC-06(05) land on one key.
    s = s.replace("[", "(").replace("]", ")")
    s = re.sub(r"\s*\(\s*", "(", s)
    s = re.sub(r"\s*\)\s*", ")", s)
    s = re.sub(r"\(([^()]*)\)", r".\1", s)
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\.+", ".", s).strip(".")
    s = _WS.sub(" ", s)
    # NIST prints the same control as AC-06(05) and AC-6(5) in adjacent label props,
    # so leading zeros inside a numeric run carry no meaning. Folding them is safe
    # only because it is applied to stored keys and queries alike; Corpus.check()
    # reports any two controls that collide once folded.
    s = re.sub(r"(?<![0-9a-z])0+(\d)", r"\1", s)
    return s


def identifier_variants(raw: str) -> List[str]:
    """Every form a person might type for one identifier, most specific first.

    Used only by exact lookup. Callers must treat the list as ordered.
    """
    base = normalise_identifier(raw)
    out = [base]

    # Separator is not meaning: ac-6.5, ac 6.5 and ac6.5 are one control.
    for v in (base.replace("-", " "), base.replace(" ", "-"), base.replace(" ", "")):
        if v and v not in out:
            out.append(v)

    # Bare numeric tail, for people who type ISM control numbers alone: "ism-421"
    # -> "421". Held to two digits or more, so GOV-01 does not offer "1" as a key
    # and turn every framework's first item into a match.
    m = re.match(r"^[a-z][a-z0-9\- ]*?[\- ](\d[\d.]*)$", base)
    if m and len(m.group(1).replace(".", "")) >= 2 and m.group(1) not in out:
        out.append(m.group(1))

    return out


# --------------------------------------------------------------------------
# Framework
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """One rung of a framework's granularity ladder, coarsest first.

    A framework can arrive at two granularities and both are wanted. An AESCSF
    assessment is performed at practice level and reported at domain level.
    """

    key: str
    name: str
    depth: int
    assessable: bool = False
    reportable: bool = False


@dataclass
class Framework:
    key: str
    name: str
    short_name: str
    publisher: str
    jurisdiction: Jurisdiction
    fidelity: Fidelity
    licence: Licence
    levels: List[Level] = field(default_factory=list)
    tier: Optional[Tier] = None
    revision: Optional[str] = None
    revision_source: Optional[str] = None
    published: Optional[str] = None
    retrieved: Optional[str] = None
    source_url: Optional[str] = None
    # The words a publisher requires alongside its text, quoted from its own copyright
    # page. Present only where a licence has actually been read; shipping text under a
    # grant that requires acknowledgement without carrying the acknowledgement is the
    # same breach as shipping it with no grant at all.
    attribution: Optional[str] = None
    source_file: Optional[str] = None
    source_files: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    intra_tier_order: int = 0

    # Retired identifiers and where the publisher says the outcome went. A search for
    # a withdrawn identifier answers with the redirect rather than with nothing.
    withdrawn_redirects: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def is_placed(self) -> bool:
        return self.tier is not None

    @property
    def sort_key(self) -> Tuple[int, int, int, str]:
        """Governance-first ordering, decided once.

        Statute, then mandated policy, then outcome, then catalogue, then
        specification. Within a tier, Australian material before American.

        An unplaced framework sorts last but is never dropped — a corpus with no tier
        is a loud warning, not a disappearance.
        """
        tier_rank = self.tier.value if self.tier is not None else 99
        return (tier_rank, self.jurisdiction.value, self.intra_tier_order, self.key)

    def level_at(self, depth: int) -> Optional[Level]:
        for lv in self.levels:
            if lv.depth == depth:
                return lv
        return None

    def warnings(self) -> List[str]:
        out = []
        if self.tier is None:
            out.append(
                "framework %r has no tier: it will sort last and be labelled unplaced "
                "in every view" % self.key
            )
        if not self.levels:
            out.append("framework %r declares no granularity levels" % self.key)
        if self.revision and not self.revision_source:
            out.append(
                "framework %r states revision %r with no source for that claim"
                % (self.key, self.revision)
            )
        if not self.source_file and not self.source_files and not self.source_url:
            out.append("framework %r cites no source document" % self.key)
        return out

    def all_source_files(self) -> List[str]:
        out = list(self.source_files)
        if self.source_file and self.source_file not in out:
            out.insert(0, self.source_file)
        return out


# --------------------------------------------------------------------------
# Control
# --------------------------------------------------------------------------


@dataclass
class Control:
    framework_key: str
    identifier: str
    text: str
    title: Optional[str] = None
    depth: int = 0
    parent_uid: Optional[str] = None
    obligation: ObligationStrength = ObligationStrength.UNKNOWN
    obligation_provenance: Provenance = Provenance.DERIVED
    applicability: Optional[object] = None
    publisher_tags: Dict[str, object] = field(default_factory=dict)
    attributes: Dict[str, object] = field(default_factory=dict)
    archetypes: List[str] = field(default_factory=list)
    section_ref: Optional[str] = None
    fidelity: Optional[Fidelity] = None
    origin: Origin = Origin.GENERATED
    superseded_key: Optional[str] = None

    identifier_key: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.identifier_key = normalise_identifier(self.identifier)

    @property
    def uid(self) -> str:
        return "%s:%s" % (self.framework_key, self.identifier_key)

    @property
    def title_is_shared(self) -> bool:
        """Set by the corpus, not guessed here. See Corpus.mark_shared_titles.

        A control title is usually a section name. All 217 PSPF titles, all 106 CSF 2.0
        titles and most ISM titles are shared between siblings, so a title is not a
        per-control label until proven unique.
        """
        return bool(self.attributes.get("_title_shared", False))

    def applicability_text(self) -> str:
        """ISM applicability is a list of classification levels; PSPF applicability is a
        sentence. Guard the type or you print 'A, l, l, , e, n, t, i, t, i, e, s'."""
        value = self.applicability
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple, set)):
            return ", ".join(str(v) for v in value)
        return str(value)

    def tag_list(self, name: str) -> List[str]:
        """Same guard for publisher tags, which are a list in one corpus and a string
        in the next."""
        value = self.publisher_tags.get(name)
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple, set)):
            return [str(v) for v in value]
        return [str(value)]


# --------------------------------------------------------------------------
# Links between controls
# --------------------------------------------------------------------------


@dataclass
class Link:
    source_uid: str
    target_uid: str
    provenance: Provenance
    basis: str
    kind: LinkKind = LinkKind.CROSS_REFERENCE
    asserted_by: Optional[str] = None
    tag_side: Optional[str] = None
    score: Optional[float] = None

    def __post_init__(self) -> None:
        if self.kind is LinkKind.INCORPORATES and self.provenance is not Provenance.PUBLISHED:
            raise ValueError(
                "link %s -> %s claims incorporation, which only an instrument can do, "
                "so it must be published" % (self.source_uid, self.target_uid)
            )
        if self.provenance is Provenance.PUBLISHED and not self.asserted_by:
            raise ValueError(
                "published link %s -> %s must name the publisher asserting it"
                % (self.source_uid, self.target_uid)
            )
        if self.provenance is Provenance.PUBLISHED_TAG and not self.tag_side:
            raise ValueError(
                "published-tag link %s -> %s must say which side, if either, was "
                "inferred" % (self.source_uid, self.target_uid)
            )
        if self.provenance is Provenance.DERIVED and self.asserted_by:
            raise ValueError(
                "derived link %s -> %s cannot name a publisher: this tool matched them "
                "on subject" % (self.source_uid, self.target_uid)
            )

    @property
    def is_citable(self) -> bool:
        return self.provenance.is_citable


# --------------------------------------------------------------------------
# Derived and published statements about a control
# --------------------------------------------------------------------------


@dataclass
class Statement:
    control_uid: str
    kind: StatementKind
    text: str
    provenance: Provenance
    archetype: Optional[str] = None
    published_by: Optional[str] = None
    published_ref: Optional[str] = None
    tier_framing: Optional[Tier] = None
    detail_uids: List[str] = field(default_factory=list)

    @property
    def is_published(self) -> bool:
        return self.provenance is Provenance.PUBLISHED

    def __post_init__(self) -> None:
        if self.provenance is Provenance.PUBLISHED and not self.published_by:
            raise ValueError(
                "published statement for %s must name its publisher: NIST's assessment "
                "objectives are never presented as this tool's" % self.control_uid
            )
        if self.provenance is Provenance.DERIVED and self.published_by:
            raise ValueError(
                "derived statement for %s cannot name a publisher" % self.control_uid
            )


# --------------------------------------------------------------------------
# Configuration detail and the guidance layer
# --------------------------------------------------------------------------


@dataclass
class Detail:
    """A product-scoped configuration recommendation.

    CIS benchmarks are not a framework column. A benchmark states how to configure one
    product, so it belongs inside the test procedure for the control it hardens, the
    same way 800-53A assessment objectives belong on an 800-53 control. Detail has no
    tier and never appears as a column.
    """

    source_key: str
    identifier: str
    title: str
    text: str
    platform: str
    profile_levels: List[str] = field(default_factory=list)
    audit: Optional[str] = None
    remediation: Optional[str] = None
    default_value: Optional[str] = None
    publisher_tags: Dict[str, object] = field(default_factory=dict)
    section_ref: Optional[str] = None
    licence: Licence = Licence.IMPORT_ONLY

    @property
    def uid(self) -> str:
        return "%s:%s" % (self.source_key, normalise_identifier(self.identifier))


@dataclass
class GuidanceDocument:
    """A publication the tool links to rather than loads.

    Guidance states no requirement of its own, or states it in a form that would be
    misread as one. It is named, cited and linked, never turned into controls.
    """

    key: str
    title: str
    publisher: str
    reason: str
    jurisdiction: Optional[Jurisdiction] = None
    url: Optional[str] = None
    source_file: Optional[str] = None
    relates_to: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Threat layer
# --------------------------------------------------------------------------


@dataclass
class Technique:
    """One way an adversary acts. Not a control, and never placed in the tier spine.

    A technique states what an attacker does; a control states what an entity must do.
    Giving them one type, or one list, is how a threat taxonomy ends up cited as an
    obligation in a finding. They are held apart here so that cannot happen by accident.
    """

    key: str
    name: str
    description: str
    tactics: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    is_sub_technique: bool = False
    parent_key: Optional[str] = None
    url: Optional[str] = None
    version: Optional[str] = None
    fidelity: Fidelity = Fidelity.OFFICIAL_MACHINE_READABLE

    @property
    def uid(self) -> str:
        return "attack:%s" % self.key.lower()


@dataclass
class Mitigation:
    """A countermeasure as the threat publisher describes it.

    Close enough to a control to be dangerous. MITRE writes these to explain what blunts
    a technique, not to be implemented and audited against, and no Australian instrument
    names them. They are held in their own collection so nothing counts one as coverage.
    """

    key: str
    name: str
    description: str
    url: Optional[str] = None
    version: Optional[str] = None
    fidelity: Fidelity = Fidelity.OFFICIAL_MACHINE_READABLE

    @property
    def uid(self) -> str:
        return "attack:%s" % self.key.lower()


@dataclass
class Mitigates:
    """A publisher's own statement that a countermeasure blunts a technique."""

    mitigation_key: str
    technique_key: str
    provenance: Provenance
    asserted_by: str
    basis: str

    def __post_init__(self) -> None:
        if self.provenance is Provenance.PUBLISHED and not self.asserted_by:
            raise ValueError(
                "published mitigates edge %s -> %s must name the publisher"
                % (self.mitigation_key, self.technique_key)
            )


@dataclass
class ThreatSource:
    """Where a threat layer came from, and whether it may be redistributed."""

    key: str
    title: str
    publisher: str
    version: str
    licence: Licence
    source_file: str
    licence_note: str = ""
    retrieved: Optional[str] = None


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


@dataclass
class Corpus:
    frameworks: Dict[str, Framework] = field(default_factory=dict)
    techniques: Dict[str, Technique] = field(default_factory=dict)
    mitigations: Dict[str, Mitigation] = field(default_factory=dict)
    mitigates: List[Mitigates] = field(default_factory=list)
    threat_sources: Dict[str, ThreatSource] = field(default_factory=dict)
    controls: Dict[str, Control] = field(default_factory=dict)
    links: List[Link] = field(default_factory=list)
    statements: List[Statement] = field(default_factory=list)
    details: Dict[str, Detail] = field(default_factory=dict)
    guidance: Dict[str, GuidanceDocument] = field(default_factory=dict)
    load_warnings: List[str] = field(default_factory=list)
    # A registered framework whose source is not in this build, keyed to why. A shipped
    # package holds nine of the eighteen: the rest load from publisher files that cannot
    # be redistributed or from extracts that are import-only. Without this the payload
    # reported "SOCI Act —" on a multi-factor query, which reads as the statute being
    # silent on multi-factor authentication rather than absent from the build.
    absent_frameworks: Dict[str, str] = field(default_factory=dict)

    # -- framework handling ------------------------------------------------

    def add_framework(self, fw: Framework) -> None:
        if fw.key in self.frameworks:
            raise ValueError("framework %r already loaded" % fw.key)
        self.frameworks[fw.key] = fw
        self.load_warnings.extend(fw.warnings())

    def ordered_frameworks(self, include_unplaced: bool = True) -> List[Framework]:
        """The one sort. Columns, diagram, coverage summary, narrative, exports and
        copy-to-markdown all consume this, so they tell the same story."""
        items = list(self.frameworks.values())
        if not include_unplaced:
            items = [f for f in items if f.is_placed]
        return sorted(items, key=lambda f: f.sort_key)

    def frameworks_in_tier(self, tier: Tier) -> List[Framework]:
        return [f for f in self.ordered_frameworks() if f.tier is tier]

    def unplaced_frameworks(self) -> List[Framework]:
        return [f for f in self.frameworks.values() if not f.is_placed]

    # -- control handling --------------------------------------------------

    def add_control(self, control: Control) -> None:
        """Merge rule: a generated corpus supersedes a shipped skeleton of the same
        key, and extra controls from either side are kept."""
        fw = self.frameworks.get(control.framework_key)
        if fw is None:
            raise ValueError(
                "control %s belongs to unloaded framework %r"
                % (control.identifier, control.framework_key)
            )
        if control.fidelity is None:
            # Set the field in place. dataclasses.replace() would store a copy here,
            # and the caller would keep mutating the original: every lettered paragraph
            # appended to a legislative subsection after this point landed on an object
            # the corpus had already thrown away, which deleted the 12- and 72-hour
            # notification clocks from the SOCI Act without a single warning.
            control.fidelity = fw.fidelity

        existing = self.controls.get(control.uid)
        if existing is None:
            self.controls[control.uid] = control
            return

        if existing.origin is Origin.SHIPPED and control.origin is Origin.GENERATED:
            control.attributes.setdefault("_superseded_shipped", True)
            self.controls[control.uid] = control
        elif existing.origin is Origin.GENERATED and control.origin is Origin.SHIPPED:
            pass  # keep the generated one; the skeleton adds nothing
        else:
            self.load_warnings.append(
                "duplicate control %s from two %s sources; kept the first"
                % (control.uid, control.origin.value)
            )

    def controls_for(self, framework_key: str) -> List[Control]:
        return [c for c in self.controls.values() if c.framework_key == framework_key]

    def control(self, uid: str) -> Optional[Control]:
        return self.controls.get(uid)

    def mark_shared_titles(self) -> None:
        """Flag every title that more than one control in the same framework carries.

        Anything treating a title as a per-control label must check this first,
        including test harnesses that generate queries from titles.
        """
        counts: Dict[Tuple[str, str], int] = {}
        for c in self.controls.values():
            if not c.title:
                continue
            key = (c.framework_key, c.title.strip().lower())
            counts[key] = counts.get(key, 0) + 1
        for c in self.controls.values():
            if not c.title:
                continue
            key = (c.framework_key, c.title.strip().lower())
            c.attributes["_title_shared"] = counts.get(key, 0) > 1

    # -- links and statements ---------------------------------------------

    # -- threat layer ------------------------------------------------------

    def add_technique(self, technique: Technique) -> None:
        if technique.key in self.techniques:
            self.load_warnings.append(
                "duplicate technique %s; kept the first" % technique.key
            )
            return
        self.techniques[technique.key] = technique

    def add_mitigation(self, mitigation: Mitigation) -> None:
        if mitigation.key in self.mitigations:
            self.load_warnings.append(
                "duplicate mitigation %s; kept the first" % mitigation.key
            )
            return
        self.mitigations[mitigation.key] = mitigation

    def add_mitigates(self, edge: Mitigates) -> None:
        if edge.mitigation_key not in self.mitigations:
            self.load_warnings.append(
                "mitigates edge names unknown mitigation %s; dropped" % edge.mitigation_key
            )
            return
        if edge.technique_key not in self.techniques:
            self.load_warnings.append(
                "mitigates edge names unknown technique %s; dropped" % edge.technique_key
            )
            return
        self.mitigates.append(edge)

    def techniques_for(self, mitigation_key: str) -> List[Technique]:
        return [
            self.techniques[e.technique_key]
            for e in self.mitigates
            if e.mitigation_key == mitigation_key and e.technique_key in self.techniques
        ]

    def mitigations_for(self, technique_key: str) -> List[Mitigation]:
        return [
            self.mitigations[e.mitigation_key]
            for e in self.mitigates
            if e.technique_key == technique_key and e.mitigation_key in self.mitigations
        ]

    def add_link(self, link: Link) -> None:
        for uid in (link.source_uid, link.target_uid):
            if uid not in self.controls:
                self.load_warnings.append(
                    "link references unknown control %s; dropped" % uid
                )
                return
        self.links.append(link)

    def links_from(
        self, uid: str, provenance: Optional[Provenance] = None
    ) -> List[Link]:
        out = [ln for ln in self.links if ln.source_uid == uid]
        if provenance is not None:
            out = [ln for ln in out if ln.provenance is provenance]
        return out

    def citable_links_from(self, uid: str) -> List[Link]:
        """What a lineage view is allowed to show."""
        return self.links_from(uid, Provenance.PUBLISHED)

    def add_statement(self, statement: Statement) -> None:
        if statement.control_uid not in self.controls:
            self.load_warnings.append(
                "statement references unknown control %s; dropped"
                % statement.control_uid
            )
            return
        self.statements.append(statement)

    def statements_for(
        self, uid: str, kind: Optional[StatementKind] = None
    ) -> List[Statement]:
        out = [s for s in self.statements if s.control_uid == uid]
        if kind is not None:
            out = [s for s in out if s.kind is kind]
        # Published first: NIST's own procedures outrank anything this tool derived.
        return sorted(out, key=lambda s: 0 if s.is_published else 1)

    # -- configuration detail and guidance ---------------------------------

    def add_detail(self, detail: Detail) -> None:
        if detail.uid in self.details:
            self.load_warnings.append("duplicate detail %s; kept the first" % detail.uid)
            return
        self.details[detail.uid] = detail

    def details_for_statement(self, statement: Statement) -> List[Detail]:
        return [
            self.details[uid] for uid in statement.detail_uids if uid in self.details
        ]

    def add_guidance(self, doc: GuidanceDocument) -> None:
        self.guidance[doc.key] = doc

    # -- integrity ---------------------------------------------------------

    def check(self) -> List[str]:
        """Problems worth shouting about at load time."""
        problems: List[str] = []
        folded: Dict[str, str] = {}
        for c in self.controls.values():
            prior = folded.get(c.uid)
            if prior is not None and prior != c.identifier:
                problems.append(
                    "IDENTIFIER COLLISION: %r and %r fold to the same key %s"
                    % (prior, c.identifier, c.uid)
                )
            folded[c.uid] = c.identifier
        for fw in self.frameworks.values():
            if not fw.is_placed:
                problems.append(
                    "UNPLACED FRAMEWORK: %s has no tier. It still appears in every "
                    "view, labelled unplaced." % fw.key
                )
            if not self.controls_for(fw.key):
                problems.append(
                    "EMPTY FRAMEWORK: %s loaded no controls. Stated gap, not a silent "
                    "one." % fw.key
                )
        for c in self.controls.values():
            if c.parent_uid and c.parent_uid not in self.controls:
                problems.append(
                    "ORPHAN: %s names parent %s, which is not loaded"
                    % (c.uid, c.parent_uid)
                )
        return problems


# --------------------------------------------------------------------------
# Ordering helpers used by every consumer
# --------------------------------------------------------------------------


def order_controls_governance_first(
    corpus: Corpus, controls: Sequence[Control]
) -> List[Control]:
    """Sort a result set once, here. The CLI, the UI and every export consume the
    result of this function rather than repeating the rule."""

    def key(c: Control) -> Tuple[int, int, int, str, str]:
        fw = corpus.frameworks.get(c.framework_key)
        if fw is None:
            return (99, 99, 99, c.framework_key, c.identifier_key)
        t, j, o, k = fw.sort_key
        return (t, j, o, k, c.identifier_key)

    return sorted(controls, key=key)


def tier_bands(corpus: Corpus) -> List[Tuple[Tier, List[Framework]]]:
    """Every tier, including empty ones.

    An empty band is drawn empty and labelled, never omitted: position in a diagram is
    an assertion, and a missing band reads as 'this question was not asked'.
    """
    return [(tier, corpus.frameworks_in_tier(tier)) for tier in Tier]
