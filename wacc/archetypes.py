"""What kind of thing a control asks for, and therefore what would show it is in place.

The axis here is evidence, not grammar. Classifying by sentence shape — passive, modal,
imperative — left 42 per cent of the corpus in an 'other' bucket, because publishers write
the same requirement in every voice: the ISM says 'Multi-factor authentication is used',
800-53 says 'Implement multi-factor authentication', the WA CSP says 'Each entity must'.
What an auditor asks is what artefact or state would demonstrate the thing is true, and
that question has a small number of answers.

Two of those answers are that there is nothing to demonstrate. A structural heading is a
place in a document, and a definition, a Ministerial power or a penalty provision is not
something an entity implements. Four hundred and forty-eight controls in this corpus are
structural containers and the SOCI Act alone holds 143 provisions conferring power on a
Minister or Secretary and 30 stating penalties. Deriving a test procedure for 'Meaning of
responsible entity' would be filler, so this module declines and says why.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .model import Control, Corpus, Tier


@dataclass
class Archetype:
    """One shape of requirement, with what proves it and what its absence exposes."""

    key: str
    label: str
    evidence: str
    test_opening: str
    risk_opening: str
    patterns: Sequence[str] = field(default_factory=tuple)
    why: str = ""
    # The shape assigned when a control plainly requires something and no more
    # specific evidence shape was recognised. Marked in the output rather than
    # hidden, so a reader can see the test was shaped by a default.
    is_fallback: bool = False

    def matches(self, text: str) -> Optional[str]:
        for pattern in self.patterns:
            found = re.search(pattern, text, re.I)
            if found:
                return " ".join(found.group(0).split())
        return None


ARCHETYPES: List[Archetype] = [
    Archetype(
        key="document",
        label="a document exists and is current",
        evidence="the document itself, its approval and the date it was last reviewed",
        test_opening="Obtain the",
        risk_opening="Nothing records what the entity has decided",
        patterns=(
            r"\b(polic(?:y|ies)|plan|procedures?|register|strategy|charter|guidelines?|"
            r"standards?|methodology|framework)\b(?![^.]*\bframework table\b)",
            r"\bis\s+(?:developed|documented|maintained|approved|established)\b",
            r"\bdocumented\b",
        ),
        why="the OAG's own finding language starts from whether the document exists",
    ),
    Archetype(
        key="configuration",
        label="a system is configured a particular way",
        evidence="the setting read off a sample of systems, and the build standard it came from",
        test_opening="Inspect the configuration of",
        risk_opening="The weakness is live on every system where the setting is wrong",
        patterns=(
            r"\b(configured|configuration|enabled|disabled|hardened|installed|deployed|"
            r"set to|turned off|turned on)\b",
            r"\b(patch(?:es|ed|ing)?|updates?|version)\b.*\b(applied|installed|used)\b",
            r"\b(encrypt(?:ed|ion)?|cipher|algorithm|key length)\b",
        ),
    ),
    Archetype(
        key="access",
        label="access is limited to those who should have it",
        evidence="the current access list, the authorised set, and the difference between them",
        test_opening="Extract the list of accounts or permissions for",
        risk_opening="More people can reach it than the entity intends",
        patterns=(
            r"\b(access is|access to|privileges?|permissions?|entitlements?)\b",
            r"\b(restricted|limited|granted|revoked|authorised|authorized|approved)\b"
            r".{0,40}\b(access|account|user|privilege)\b",
            r"\b(multi-?factor|authenticat\w+|credential|password|passphrase)\b",
        ),
    ),
    Archetype(
        key="record",
        label="a record is generated and kept",
        evidence="the records themselves for a sampled period, and the retention setting",
        test_opening="Obtain the records for a sampled period from",
        risk_opening="If it happened, nobody can show what happened or when",
        patterns=(
            r"\b(logged|logging|log records?|event logs?|audit (?:records?|logs?|trail)|"
            r"retained|retention)\b",
            r"\b(records? (?:are|is|must be)|evidence (?:is|are))\b",
        ),
    ),
    Archetype(
        key="periodic",
        label="something happens on a cycle",
        evidence="the last several instances and the dates between them",
        test_opening="Obtain the last three instances of",
        risk_opening="Between one cycle and the next nothing detects drift",
        patterns=(
            r"\b(annually|periodic(?:ally)?|regularly|at least every|at least annually|"
            r"each year|every \d+|ongoing basis)\b",
            r"\b(reviewed|reassessed|revalidated|re-?tested|audited)\b",
        ),
    ),
    Archetype(
        key="notification",
        label="somebody is told, within a time",
        evidence="a sample of events, when each was detected and when each was reported",
        test_opening="Sample events and measure the elapsed time between detection and "
                     "the report required by",
        risk_opening="The people who need to act are not told in time to act",
        patterns=(
            r"\b(report(?:s|ed|ing)?|notif(?:y|ies|ied|ication)|advise[sd]?|inform(?:ed)?|"
            r"escalat\w+)\b.{0,60}\b(to|within)\b",
            r"\bwithin \d+ (?:hours?|days?|minutes?)\b",
        ),
    ),
    Archetype(
        key="responsibility",
        label="a named person or role is answerable",
        evidence="the appointment, and that the person can describe what they are answerable for",
        test_opening="Confirm the appointment and current occupant of the role named in",
        risk_opening="No one is answerable, so nothing forces a decision",
        patterns=(
            r"\b(accountable|responsible for|appoint\w*|designat\w*|assigned to)\b",
            r"\b(accountable authority|chief information security officer|ciso|"
            r"cyber security executive|board|executive committee|system owners?|"
            r"data owners?|authorising officer|authorizing official)\b",
        ),
    ),
    Archetype(
        key="training",
        label="people are taught something",
        evidence="the course content, the attendance records and the completion rate",
        test_opening="Obtain attendance and completion records for",
        risk_opening="People act on what they were never told",
        patterns=(
            r"\b(train(?:ing|ed)?|awareness|educat\w+|induction|upskill\w*|competenc\w+)\b",
        ),
    ),
    Archetype(
        key="activity",
        label="an activity is carried out",
        is_fallback=True,
        evidence="evidence that the activity ran over a sampled period, and its output",
        test_opening="Obtain evidence that the activity ran, for a sampled period, in",
        risk_opening="The work is not being done",
        patterns=(
            r"\b(assessed?|assessment|performed|conducted|undertaken|carried out|"
            r"scanning|scanned|tested|testing|backups?|backed up|restor\w+|exercis\w+|"
            r"select(?:s|ed|ion)?|analys\w+|analyz\w+|captur\w+|remediat\w+|"
            r"validat\w+|verif\w+|acquir\w+|dispos\w+|sanitis\w+|sanitiz\w+)\b",
        ),
    ),
    Archetype(
        key="prohibition",
        label="something must not happen",
        evidence="a search for instances of the prohibited thing, not an assurance that it is absent",
        test_opening="Search for instances of the prohibited condition described in",
        risk_opening="The thing the control forbids is free to occur",
        patterns=(
            r"\b(must not|shall not|may not|cannot|is not permitted|are not permitted|"
            r"prohibited|disallowed|denied|prevented from|blocked)\b",
        ),
        why="a negation is never the optional half of a pattern, here or in retrieval",
    ),
    Archetype(
        key="outcome",
        label="a state of affairs holds",
        evidence="whether the stated outcome obtains, and by what means the entity achieves it",
        test_opening="Establish whether the outcome stated in",
        risk_opening="The outcome is not achieved, and nothing the entity holds says how it would be",
        patterns=(
            r"^[^.]{0,120}\b(?:is|are)\s+(?:not\s+)?[a-z]+(?:ed|d)\b",
            r"\b(?:systems?|data|information|assets?|events?|incidents?|risks?|"
            r"personnel|networks?|services?)\b[^.]{0,80}\b(?:is|are)\b",
            r"\bonly\s+(?:permit|allow)\w*\b",
        ),
        why=(
            "the ISM's 41 cyber security principles, the CSF's 106 subcategories and most "
            "AESCSF practices state a required state of affairs rather than an action. "
            "They are testable, at the level of whether the state obtains; without this "
            "shape half the corpus fell through with no test at all"
        ),
    ),
]

ARCHETYPES_BY_KEY = {a.key: a for a in ARCHETYPES}


# -- what is not a requirement at all --------------------------------------

@dataclass
class NotDerivable:
    reason: str
    detail: str


_DEFINITION = re.compile(
    r"^\s*(meaning of|definitions?|interpretation|simplified outline|application of "
    r"(?:this|the)|object(?:s)? of (?:this|the))\b", re.I
)
_DEFINES = re.compile(r"\b(means|has the same meaning as|is taken to be)\b")
_OFFICE_HOLDER = re.compile(
    r"\b(the Minister|the Secretary|the Prime Minister|the Commissioner|the Inspector-"
    r"General|the Department)\b"
)
_ENTITY_ACTOR = re.compile(
    r"\b(entity|entities|organisation|organization|agency|agencies|responsible entity|"
    r"system owner|personnel|users?|supplier|service provider)\b", re.I
)
_PENALTY = re.compile(r"\b(civil penalty|penalty units|is guilty of an offence)\b", re.I)


# A subsection inherits the nature of the section it sits in. SOCI s 12L(1) reads as an
# assertion about the world — 'The responsible entity for a critical telecommunications
# asset is...' — and on its own text alone it classified as an outcome and produced a risk
# statement saying the outcome was not achieved. Its ancestors say what it is: Part 1
# Preliminary, Division 2 Definitions, s 12L Meaning of responsible entity.
_DEFINING_ANCESTOR = re.compile(
    r"^\s*(definitions?|interpretation|preliminary|meaning of|dictionary|"
    r"simplified outline)\b", re.I
)


def not_derivable(
    control: Control, ancestors: Sequence[Control] = ()
) -> Optional[NotDerivable]:
    """Whether this entry states nothing an entity could be tested against."""
    title = (control.title or "").strip()
    text = " ".join((control.text or "").split())
    whole = ("%s %s" % (title, text)).strip()

    if control.attributes.get("structural"):
        return NotDerivable(
            "structural",
            "a heading that holds other provisions rather than stating a requirement",
        )
    # Nearest first: 's 12L Meaning of responsible entity' tells a reader more than
    # 'Part 1 Preliminary', and both are true of the same subsection.
    for ancestor in reversed(list(ancestors)):
        heading = (ancestor.title or "").strip()
        if heading and _DEFINING_ANCESTOR.match(heading):
            return NotDerivable(
                "definition",
                "this sits under %s %s, which fixes the meaning of terms rather than "
                "requiring anything" % (ancestor.identifier, heading),
            )
    if not text or len(text) < 12:
        return NotDerivable("no text", "this entry carries no requirement text to test")
    if _DEFINITION.match(title) or _DEFINITION.match(text):
        return NotDerivable(
            "definition", "this provision fixes the meaning of a term rather than "
            "requiring anything"
        )
    if _DEFINES.search(text[:240]) and not _ENTITY_ACTOR.search(text[:240]):
        return NotDerivable(
            "definition", "this provision defines a term rather than requiring anything"
        )
    if _PENALTY.search(whole) and not _ENTITY_ACTOR.search(text[:200]):
        return NotDerivable(
            "penalty", "this provision states a consequence of non-compliance rather "
            "than a thing to do"
        )
    if _OFFICE_HOLDER.search(text[:220]) and not _ENTITY_ACTOR.search(text[:220]):
        return NotDerivable(
            "power of an office holder",
            "this provision confers a power or duty on a Minister, Secretary or "
            "regulator, not on the entity being audited",
        )
    return None


def classify(
    control: Control, ancestors: Sequence[Control] = ()
) -> Tuple[List[Archetype], List[str], Optional[NotDerivable]]:
    """Which shapes this control has, the phrase that showed each, and any refusal.

    A control can have several. 'Event logs are retained for at least 90 days and
    reviewed annually' is a record, a periodic activity and a threshold at once, and
    forcing one archetype would lose two thirds of the test.
    """
    refusal = not_derivable(control, ancestors)
    if refusal is not None:
        return [], [], refusal
    text = "%s. %s" % (control.title or "", control.text or "")
    found: List[Archetype] = []
    evidence: List[str] = []
    for archetype in ARCHETYPES:
        hit = archetype.matches(text)
        if hit:
            found.append(archetype)
            evidence.append(hit)
    if not found:
        # A control that states a requirement and matches no evidence shape is still an
        # activity somebody performs: 'System owners obtain an authorisation to operate
        # for each system' is tested by obtaining the authorisations. Chasing this with
        # more verbs turns the classifier into a word list nobody can reason about, so
        # the general case is stated once, here, and flagged.
        found = [ARCHETYPES_BY_KEY["activity"]]
        evidence = ["no more specific evidence shape was recognised"]
    return found, evidence, None
