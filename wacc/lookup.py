"""Exact identifier lookup, on its own path.

An identifier is not a word and must never be scored like one. Typing AC-6(5) is a
request for one control, and the honest answers are that control, a named set of
candidates, a redirect, or nothing. A ranked list of things that mention privileged
accounts is not among them.

Nothing here uses prefix matching. PSPF Req 93 shares its prefix with every other PSPF
requirement, so a prefix search answers 'Req 9' with ten requirements and calls it a
match. Keys are compared whole.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .model import (
    Control,
    Corpus,
    identifier_variants,
    normalise_identifier,
    order_controls_governance_first,
)

# Words that name a framework, so 'CIRMP s 8(4)' resolves where 's 8(4)' cannot.
FRAMEWORK_WORDS: Dict[str, str] = {
    "ism": "ism",
    "acsc": "ism",
    "asd": "ism",
    "pspf": "pspf",
    "soci": "soci-act",
    "cirmp": "cirmp-rules",
    "csf": "csf",
    "nist": "nist-800-53",
    "cis": "cis-controls",
    "aescsf": "aescsf",
    "oag": "oag-wa",
    "wa": "wa-csp",
    "circular": "wa-circular",
    "fips": "fips-140-3",
}

_HAS_DIGIT = re.compile(r"\d")
_WORD = re.compile(r"[a-z]+")

# An identifier is short, contains a digit, and is not a sentence.
MAX_IDENTIFIER_WORDS = 5
MAX_IDENTIFIER_CHARS = 48


class Status:
    UNIQUE = "unique"
    AMBIGUOUS = "ambiguous"
    WITHDRAWN = "withdrawn"
    NONE = "none"
    NOT_AN_IDENTIFIER = "not-an-identifier"


@dataclass
class Redirect:
    framework_key: str
    identifier: str
    targets: List[str]
    resolved: List[Control] = field(default_factory=list)


@dataclass
class LookupResult:
    query: str
    normalised: str
    status: str
    matches: List[Control] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)
    matched_form: Optional[str] = None
    framework_filter: Optional[str] = None
    note: Optional[str] = None

    @property
    def is_decisive(self) -> bool:
        return self.status in (Status.UNIQUE, Status.WITHDRAWN)


def looks_like_identifier(query: str) -> bool:
    """Whether the identifier path should be tried at all.

    'multi-factor authentication' contains a digit in neither sense and is four words of
    prose; running it through exact lookup wastes a step and, worse, invites a bare-token
    match on something like '2'.
    """
    text = (query or "").strip()
    if not text or len(text) > MAX_IDENTIFIER_CHARS:
        return False
    if not _HAS_DIGIT.search(text):
        return False
    return len(text.split()) <= MAX_IDENTIFIER_WORDS


class IdentifierIndex:
    """Every form of every stored identifier, mapped to the controls that own it.

    Two tiers. A primary key is the control's own normalised identifier. An alias is any
    other form a person might type for it — separator variants, the bare number, and the
    publisher's alternate labels. A primary hit always beats an alias hit, so typing
    '3.10' cannot be answered by something whose bare tail happens to be 3.10.
    """

    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        self.primary: Dict[str, List[str]] = {}
        self.alias: Dict[str, List[str]] = {}
        self.redirects: List[Redirect] = []
        self._build()

    def _add(self, table: Dict[str, List[str]], key: str, uid: str) -> None:
        if not key:
            return
        bucket = table.setdefault(key, [])
        if uid not in bucket:
            bucket.append(uid)

    def _build(self) -> None:
        for uid, control in self.corpus.controls.items():
            self._add(self.primary, control.identifier_key, uid)
            for variant in identifier_variants(control.identifier):
                if variant != control.identifier_key:
                    self._add(self.alias, variant, uid)
            alternates = control.attributes.get("alternate_labels")
            if isinstance(alternates, list):
                for label in alternates:
                    for variant in identifier_variants(str(label)):
                        self._add(self.alias, variant, uid)

        for framework in self.corpus.frameworks.values():
            for identifier, targets in framework.withdrawn_redirects.items():
                self.redirects.append(
                    Redirect(
                        framework_key=framework.key,
                        identifier=identifier,
                        targets=list(targets),
                    )
                )

    # -- lookup ------------------------------------------------------------

    def find(self, query: str) -> LookupResult:
        raw = (query or "").strip()
        if not looks_like_identifier(raw):
            return LookupResult(
                query=raw,
                normalised=normalise_identifier(raw),
                status=Status.NOT_AN_IDENTIFIER,
                note="not identifier-shaped; this query belongs to topical search",
            )

        framework_key, stripped = self._framework_qualifier(raw)
        if ':' in raw:
            prefix, identifier = raw.split(':', 1)
            if prefix.casefold() in self.corpus.frameworks:
                framework_key, stripped = prefix.casefold(), identifier
        normalised = normalise_identifier(stripped)
        if framework_key:
            direct = self.corpus.control(framework_key + ':' + normalised)
            if direct is not None:
                return LookupResult(query=raw, normalised=normalised, status=Status.UNIQUE,
                                    matches=[direct], matched_form=normalised,
                                    framework_filter=framework_key)
        forms = identifier_variants(stripped)

        uids, matched_form = self._collect(forms)
        controls = [self.corpus.controls[u] for u in uids if u in self.corpus.controls]

        if framework_key:
            narrowed = [c for c in controls if c.framework_key == framework_key]
            if narrowed:
                controls = narrowed

        if controls:
            controls = order_controls_governance_first(self.corpus, controls)
            status = Status.UNIQUE if len(controls) == 1 else Status.AMBIGUOUS
            note = None
            if status is Status.AMBIGUOUS:
                names = ", ".join(
                    "%s %s"
                    % (self.corpus.frameworks[c.framework_key].short_name, c.identifier)
                    for c in controls
                )
                note = (
                    "%d controls carry this identifier (%s). Name the framework to "
                    "narrow it." % (len(controls), names)
                )
            return LookupResult(
                query=raw,
                normalised=normalised,
                status=status,
                matches=controls,
                matched_form=matched_form,
                framework_filter=framework_key,
                note=note,
            )

        found = self._withdrawn(forms, framework_key)
        if found:
            return LookupResult(
                query=raw,
                normalised=normalised,
                status=Status.WITHDRAWN,
                redirects=found,
                framework_filter=framework_key,
                note=_redirect_note(found),
            )

        return LookupResult(
            query=raw,
            normalised=normalised,
            status=Status.NONE,
            framework_filter=framework_key,
            note=(
                "no control carries this identifier. It is well-formed, so this is an "
                "absence in the corpus rather than a typo the tool can correct."
            ),
        )

    # -- internals ---------------------------------------------------------

    def _collect(self, forms: Sequence[str]) -> Tuple[List[str], Optional[str]]:
        for form in forms:
            if form in self.primary:
                return list(self.primary[form]), form
        for form in forms:
            if form in self.alias:
                return list(self.alias[form]), form
        return [], None

    def _withdrawn(
        self, forms: Sequence[str], framework_key: Optional[str]
    ) -> List[Redirect]:
        wanted = {normalise_identifier(f) for f in forms}
        out: List[Redirect] = []
        for redirect in self.redirects:
            if framework_key and redirect.framework_key != framework_key:
                continue
            if normalise_identifier(redirect.identifier) not in wanted:
                continue
            resolved: List[Control] = []
            for target in redirect.targets:
                uid = "%s:%s" % (redirect.framework_key, normalise_identifier(target))
                control = self.corpus.control(uid)
                if control is not None:
                    resolved.append(control)
            out.append(
                Redirect(
                    framework_key=redirect.framework_key,
                    identifier=redirect.identifier,
                    targets=list(redirect.targets),
                    resolved=resolved,
                )
            )
        return out

    def _framework_qualifier(self, raw: str) -> Tuple[Optional[str], str]:
        """Pull a leading framework word off the query, if one is there.

        Only a word that is not part of the identifier itself counts. 'ISM-0421' keeps
        its prefix, because the prefix is the identifier; 'CIRMP s 8(4)' loses it,
        because there the word is a qualifier.
        """
        tokens = raw.split()
        if len(tokens) < 2:
            return None, raw
        head = _WORD.match(tokens[0].lower())
        if not head:
            return None, raw
        word = head.group(0)
        if word not in FRAMEWORK_WORDS:
            return None, raw
        if _HAS_DIGIT.search(tokens[0]):
            # 'ISM-0421' — the word is welded to the number and is the identifier.
            return None, raw
        return FRAMEWORK_WORDS[word], " ".join(tokens[1:])


def _redirect_note(redirects: List[Redirect]) -> str:
    parts = []
    for redirect in redirects:
        targets = ", ".join(redirect.targets) or "nothing named"
        parts.append("%s was withdrawn; the publisher points to %s"
                     % (redirect.identifier, targets))
    return ". ".join(parts)
