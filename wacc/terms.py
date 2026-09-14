"""The vocabulary layer.

Two publishers write the same requirement in different words, and the crosswalk is worth
nothing if it cannot see that. This is where those words are reconciled, once, so no
loader or ranker reconciles them again privately.

Four rules, each of which exists because breaking it produced a real defect.

Spelling is folded in one place. NIST writes 'Media Sanitization' and the ISM writes
'sanitisation'; the fold is applied to indexed text and to queries alike, so no term is
ever stored twice in two spellings.

Stemming is restricted to inflections that actually occur. Stripping four trailing
letters lets 'account' match 'Accountable Authority'. Nothing here removes more than
three characters, and nothing is stemmed below three.

Aliases match tokens, never substrings. The alias 'OT' inside 'bluetooth' is not a match
for operational technology, and the only reliable defence is to compare whole tokens.

A negation is never the optional part of a pattern. Making 'not' optional to broaden a
prohibition turns every positive statement into a prohibition.
"""

import re
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# The hyphen is a separator, not part of a token. SQLite's unicode61 tokeniser splits
# there whatever this module does, and keeping 'multi-factor' whole meant the indexed
# text and the query never agreed: a search for 'multi factor authentication' and one
# for 'multi-factor authentication' returned different results for the same question.
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")
_WS = re.compile(r"\s+")

MIN_STEM_LENGTH = 3
# Four-letter words are stemmed. 'logs' has to reach 'log', and holding the threshold
# one letter higher left every four-letter plural stranded from its singular.
MIN_WORD_TO_STEM = 4

# Retrieval terms only. Obligation words such as 'must' and 'not' are dropped here
# because they say nothing about subject; the patterns that read obligation strength
# work on the original text, where a negation is never optional.
STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "do", "does", "each", "for", "from", "had", "has", "have", "if", "in",
    "into", "is", "it", "its", "may", "must", "not", "of", "on", "only", "or",
    "other", "shall", "should", "such", "than", "that", "the", "their", "then",
    "there", "these", "this", "those", "to", "was", "were", "when", "where", "which",
    "will", "with", "would",
    # Question words. A person asking 'how quickly must an incident be reported' is not
    # searching for the word how, and treating it as a term matched the OAG heading
    # 'Understand how accounts are used'.
    "how", "what", "who", "whom", "whose", "why", "quickly", "soon", "long", "many",
    "much", "should", "shall", "need", "needs",
}


# --------------------------------------------------------------------------
# Spelling
# --------------------------------------------------------------------------

# Words ending in -ise that are spelled -ise on both sides of the Pacific. Folding
# these to -ize would invent words and, worse, would make 'advise' and 'advice'
# drift apart from the text they came from.
_KEEP_ISE = {
    "advise", "advertise", "arise", "chastise", "circumcise", "comprise", "compromise",
    "concise", "demise", "despise", "devise", "disguise", "excise", "exercise",
    "franchise", "improvise", "incise", "merchandise", "otherwise", "precise",
    "premise", "promise", "revise", "rise", "supervise", "surmise", "surprise",
    "televise", "wise",
}

_SPELLING_WORDS = {
    "analyse": "analyze", "analysed": "analyzed", "analyses": "analyzes",
    "analysing": "analyzing", "analyser": "analyzer",
    "paralyse": "paralyze", "catalogue": "catalog", "dialogue": "dialog",
    "licence": "license", "licenced": "licensed", "licencing": "licensing",
    "defence": "defense", "offence": "offense", "practise": "practice",
    "centre": "center", "centres": "centers", "metre": "meter", "fibre": "fiber",
    "programme": "program", "programmes": "programs",
    "behaviour": "behavior", "behavioural": "behavioral",
    "colour": "color", "favour": "favor", "labour": "labor", "neighbour": "neighbor",
    "organisation": "organization", "organisational": "organizational",
    "authorise": "authorize", "authorised": "authorized", "authorisation": "authorization",
    "utilise": "utilize", "utilised": "utilized",
    "enrol": "enroll", "enrolment": "enrollment",
    "fulfil": "fulfill", "fulfilment": "fulfillment",
    "judgement": "judgment", "acknowledgement": "acknowledgment",
    "storey": "story", "grey": "gray",
}

_ISE_SUFFIXES = (
    ("isation", "ization"),
    ("isations", "izations"),
    ("ising", "izing"),
    ("ised", "ized"),
    ("iser", "izer"),
    ("isers", "izers"),
    ("ises", "izes"),
    ("ise", "ize"),
)


# One word family, one stem. Folding the spelling is not enough on its own: the ISM
# writes 'sanitised', NIST writes 'Media Sanitization', and after the -ise fold those
# still land on sanitiz and sanitization, which never meet. Everything in this family
# reduces to the -iz root instead, which is a closed derivation rather than the generic
# suffix stripping the stemmer is deliberately barred from doing.
_IZ_SUFFIXES = (
    "izational", "izations", "ization", "izing", "izers", "izer", "izes", "ized", "ize",
)
MIN_IZ_ROOT = 3


def _fold_iz_family(word: str) -> str:
    for suffix in _IZ_SUFFIXES:
        if not word.endswith(suffix):
            continue
        root = word[: -len(suffix)]
        if len(root) < MIN_IZ_ROOT:
            # 'size', 'prize' and 'seize' end in -ize and are not this family.
            return word
        return root + "iz"
    return word


def fold_spelling(word: str) -> str:
    """Reduce a word to one spelling. Applied to indexed text and to queries alike."""
    lower = word.lower()
    if lower in _KEEP_ISE:
        return lower
    if lower in _SPELLING_WORDS:
        return _fold_iz_family(_SPELLING_WORDS[lower])
    for british, american in _ISE_SUFFIXES:
        if lower.endswith(british) and len(lower) > len(british) + 1:
            root = lower[: -len(british)]
            if root + "ise" in _KEEP_ISE or root + "se" in _KEEP_ISE:
                return lower
            return _fold_iz_family(root + american)
    if lower.endswith("our") and len(lower) > 5:
        return lower[:-3] + "or"
    return _fold_iz_family(lower)


# --------------------------------------------------------------------------
# Inflection
# --------------------------------------------------------------------------

_SUFFIXES: Tuple[Tuple[str, str], ...] = (
    ("ies", "y"),
    ("ied", "y"),
    ("ing", ""),
    ("ed", ""),
    ("es", ""),
    ("s", ""),
)

# 'es' is only a plural ending after a sibilant — boxes, matches, processes. Everywhere
# else the plural is a bare s on a word that already ends in e, so stripping 'es' from
# 'privileges' produced privileg while 'privilege' stayed whole, and the two halves of
# one word never met. The privileged-access concept could not fire on its own query.
_SIBILANTS = ("s", "x", "z", "ch", "sh")

# '-ation' is the noun of an '-ate' verb, and splitting the pair left 'authentication'
# unable to match 'Use MFA to authenticate privileged users'. Both sides of the search
# get the same transform, so a root that is not a word ('informat') costs nothing; what
# matters is that the family lands in one place.
_ATION = ("ations", "ation")


def _drop_silent_e(root: str) -> str:
    """One trailing e, dropped last, so store and stored land together.

    English hides the same split in both directions: the plural of a word ending in e
    adds s, and its past tense adds d. Stripping the inflection leaves store and stor
    apart. Removing the final e after the inflection collapses the pair, and it is one
    character, well inside what this module allows itself to remove.
    """
    if root.endswith("e") and len(root) - 1 >= MIN_STEM_LENGTH:
        return root[:-1]
    return root


def stem(word: str) -> str:
    """Strip a real inflection and nothing else.

    'vulnerability' and 'vulnerabilities' must land on one stem, because consonant plus
    y becomes ies and that pattern covers entity, activity, policy, capability,
    authority and facility as well.
    """
    lower = word.lower()
    if len(lower) < MIN_WORD_TO_STEM:
        return lower
    for suffix in _ATION:
        if lower.endswith(suffix) and len(lower) - len(suffix) + 2 >= MIN_STEM_LENGTH:
            return lower[: -len(suffix)] + "at"
    for suffix, replacement in _SUFFIXES:
        if not lower.endswith(suffix):
            continue
        if suffix == "s" and lower.endswith("ss"):
            # 'access' is not a plural.
            continue
        root = lower[: -len(suffix)] + replacement
        if suffix == "es" and not root.endswith(_SIBILANTS):
            # 'privileges' is privilege plus s, not privileg plus es.
            continue
        if len(root) < MIN_STEM_LENGTH:
            continue
        if suffix in ("ing", "ed"):
            root = _undouble(root)
        return _drop_silent_e(root)
    return _drop_silent_e(lower)


def _undouble(root: str) -> str:
    """'logging' becomes log, not logg. 'processing' stays process, not proces."""
    if len(root) >= 4 and root[-1] == root[-2] and root[-1] not in "s":
        return root[:-1]
    return root


# Pure, and called once per word of every control at index time and once per word of
# every query. The corpus holds a few tens of thousands of distinct words, so the
# cache is small and it removes most of the cost of both.
@lru_cache(maxsize=200000)
def normalise_token(word: str) -> str:
    return stem(fold_spelling(word))


def tokenise(text: str) -> List[str]:
    return _TOKEN.findall((text or "").lower())


def normalise_text(text: str) -> List[str]:
    return [normalise_token(t) for t in tokenise(text)]


def content_stems(text: str) -> List[str]:
    """Normalised stems with stopwords removed, for retrieval and scoring."""
    return [s for s in normalise_text(text) if s and s not in STOPWORDS]


# --------------------------------------------------------------------------
# Aliases — token to token, never substring
# --------------------------------------------------------------------------

ALIASES: Dict[str, List[str]] = {
    "mfa": ["multi-factor", "authentication"],
    "2fa": ["two-factor", "authentication"],
    "e8": ["essential", "eight"],
    "ism": ["information", "security", "manual"],
    "pspf": ["protective", "security", "policy", "framework"],
    "soci": ["security", "critical", "infrastructure"],
    "cirmp": ["critical", "infrastructure", "risk", "management", "program"],
    "csf": ["cybersecurity", "framework"],
    "oag": ["auditor", "general"],
    "ot": ["operational", "technology"],
    "it": [],
    "aal": ["authentication", "assurance", "level"],
    "ial": ["identity", "assurance", "level"],
    "fal": ["federation", "assurance", "level"],
    "ce": ["cryptographic", "erase"],
    "rto": ["recovery", "time", "objective"],
    "rpo": ["recovery", "point", "objective"],
    "siem": ["security", "information", "event", "management"],
    "mdm": ["mobile", "device", "management"],
    "ad": ["active", "directory"],
    "ca": ["certificate", "authority"],
    "sed": ["self-encrypting", "drive"],
}

# An alias this short only fires as a whole token, and only when the query is short
# enough that the person plainly meant the abbreviation.
SHORT_ALIAS_MAX_QUERY_TOKENS = 4
SHORT_ALIAS_LENGTH = 3


def alias_alternatives(tokens: Sequence[str]) -> List[Tuple[str, List[List[str]]]]:
    """Each query token with the forms that mean the same thing.

    An expansion is an alternative spelling of one term, not a set of extra terms. A
    person who types MFA has named one subject, and a control saying 'multi-factor
    authentication' answers it in full. Scoring the expansion as three additional terms
    marked that control two-thirds absent and buried it.

    Each alternative is a list of stems that must all be present for the alternative to
    count, so the expansion of MFA is one alternative of three stems, not three of one.
    """
    out: List[Tuple[str, List[List[str]]]] = []
    for token in tokens:
        forms = [[normalise_token(token)]]
        expansion = ALIASES.get(token)
        if expansion and not (
            len(token) <= SHORT_ALIAS_LENGTH
            and len(tokens) > SHORT_ALIAS_MAX_QUERY_TOKENS
        ):
            # An alias value may itself be written with a hyphen; run it through the
            # same tokeniser as everything else so the forms are comparable.
            stems = [st for word in expansion for st in normalise_text(word)]
            if stems and stems not in forms:
                forms.append(stems)
        out.append((token, forms))
    return out


def expand_aliases(tokens: Sequence[str]) -> List[str]:
    """Add each alias expansion as extra tokens. The original token is kept."""
    out: List[str] = list(tokens)
    for token in tokens:
        expansion = ALIASES.get(token)
        if not expansion:
            continue
        if len(token) <= SHORT_ALIAS_LENGTH and len(tokens) > SHORT_ALIAS_MAX_QUERY_TOKENS:
            # 'ad' in a long sentence is far more likely to be a word than Active
            # Directory. Short aliases only fire when the query is plainly the
            # abbreviation.
            continue
        out.extend(expansion)
    return out


# --------------------------------------------------------------------------
# Concepts — the same subject under different names
# --------------------------------------------------------------------------


class Concept:
    """One subject, the phrases publishers use for it, and what it is not.

    `excluding` exists because a phrase can carry a term without carrying the subject.
    'TOP SECRET-Privileged Access' is a PSPF clearance level, and counting it as a
    privileged access control puts a personnel security requirement in a technical
    finding.
    """

    def __init__(
        self,
        key: str,
        phrases: Sequence[str],
        excluding: Sequence[str] = (),
        control_phrases: Optional[Sequence[str]] = None,
        why: str = "",
    ) -> None:
        self.key = key
        self.phrases = [p.lower() for p in phrases]
        self.excluding = [e.lower() for e in excluding]
        # What the phrases mean on each side of the search. `phrases` is what makes a
        # query name this concept. `control_phrases` is what counts as this concept in a
        # control, and differs only for a group: naming one Essential Eight strategy has
        # to reach a policy that mandates the group, but it must not reach the other
        # seven strategies, and matching the member phrases in controls did exactly that
        # — an application control query answered with multi-factor authentication.
        self.control_phrases = [
            p.lower() for p in (phrases if control_phrases is None else control_phrases)
        ]
        self.why = why

    @property
    def stems(self) -> List[List[str]]:
        return [normalise_text(p) for p in self.phrases]

    @property
    def control_stems(self) -> List[List[str]]:
        return [normalise_text(p) for p in self.control_phrases]


CONCEPTS: List[Concept] = [
    Concept(
        "media-sanitisation",
        [
            "sanitisation", "sanitization", "sanitise", "sanitize",
            "secure disposal", "media disposal", "disposal of media",
            "degauss", "degaussing", "purge", "destruction of media",
            "destroy media", "media destruction", "cryptographic erase",
        ],
        why="the ISM says sanitisation, NIST says sanitization, the WA CSP says secure disposal",
    ),
    Concept(
        "event-logging",
        [
            "event log", "event logging", "audit log", "log record",
            "logging", "log retention", "centralised logging", "log monitoring",
        ],
        why="CSF 2.0 says 'Log records are generated' and never writes 'event log'",
    ),
    Concept(
        "application-control",
        [
            "application control", "application allowlisting", "application allow list",
            "allowlisting", "whitelisting", "authorized software",
            "unapproved software", "execution of unauthorized software",
            "allow-by-exception",
        ],
        why="800-53 titles CM-7(5) 'Authorized Software — Allow-by-exception'",
    ),
    Concept(
        "multi-factor-authentication",
        ["multi-factor authentication", "multifactor authentication",
         "two-factor authentication", "mfa", "second factor"],
        why="spelled with and without the hyphen in adjacent paragraphs of the same document",
    ),
    Concept(
        "privileged-access",
        [
            "privileged access", "privileged account", "privileged user",
            "administrative privilege", "administrator account", "least privilege",
            "elevated privilege", "domain admin",
        ],
        excluding=["top secret-privileged access", "privileged access clearance"],
        why="the PSPF clearance level TOP SECRET-Privileged Access is not a technical control",
    ),
    Concept(
        "backup",
        ["backup", "back up", "restoration", "restore", "recovery point objective",
         "recovery time objective"],
        why="",
    ),
    Concept(
        "patching-and-vulnerabilities",
        [
            "patch", "patching", "patch management", "security update",
            "vulnerability", "vulnerability management", "vulnerability remediation",
            "vulnerability scanning", "mitigating known vulnerabilities",
            "known exploited vulnerability", "security fix", "update applications",
            "update operating systems", "end of support", "unsupported software",
        ],
        why=(
            "one subject under two vocabularies. ASD writes 'patch applications', the "
            "ISM writes 'vulnerabilities identified in software are resolved', CSF "
            "writes 'vulnerabilities in assets are identified'. Keeping patching and "
            "vulnerability apart left ISM-1754 unreachable from a patching query and "
            "ID.RA-01 unreachable from a vulnerability one"
        ),
    ),
    Concept(
        "incident-notification",
        ["report a cyber security incident", "notify of a cyber security incident",
         "incident reporting", "incident notification", "notifiable incident"],
        why="",
    ),
    Concept(
        "essential-eight",
        [
            "essential eight",
            "application control", "patch applications", "configure microsoft office macro settings",
            "user application hardening", "restrict administrative privileges",
            "patch operating systems", "multi-factor authentication", "regular backups",
        ],
        control_phrases=["essential eight", "essential 8"],
        why=(
            "the WA CSP mandates the Essential Eight without naming any of the eight, so "
            "a query for one strategy only reaches WA CSP 3.1.1a through this group"
        ),
    ),
    Concept(
        "cryptography",
        [
            "approved cryptography", "cryptography", "cryptographic protection",
            "cryptographic algorithm", "cryptographic protocol",
            "key length", "key size", "key management", "cryptoperiod", "encryption key",
            "security strength", "cipher", "cipher suite", "aes", "rsa", "ecdsa", "sha",
            "tls", "hashing algorithm", "digital signature",
        ],
        why=(
            "a publisher states this subject by naming the primitive. ISM-1369 is "
            "'AES-GCM is used for encryption of TLS connections' and carries none of "
            "the words a person types when asking about approved algorithms. The bare "
            "words encryption and encrypted are deliberately absent: with them, CIS "
            "3.9 'Encrypt Data on Removable Media' answered a question about approved "
            "algorithms and key lengths, which it does not address"
        ),
    ),
    Concept(
        "supply-chain",
        ["supply chain", "third party", "third-party", "supplier",
         "service provider", "outsourced", "outsourcing", "vendor", "subcontractor"],
        excluding=["carriage service provider", "carriage service"],
        why=(
            "SOCI s 12L defines a responsible entity by reference to a carriage service "
            "provider. That is who the entity is, not a requirement about its suppliers, "
            "and without the exclusion it took slot one on a supply-chain query"
        ),
    ),
    Concept(
        "cybersecurity-governance",
        ["cybersecurity governance", "cyber security governance", "cybersecurity program",
         "cyber security program", "risk management strategy", "accountable authority",
         "risk executive", "govern function"],
        why="governance appears as a PSPF responsibility, an AESCSF program and an 800-53 risk-management function",
    ),
    Concept(
        "personnel-security",
        ["personnel security", "personnel screening", "pre-employment screening",
         "background check", "personnel termination", "personnel transfer", "rescreening"],
        why="the subject spans checks before access and access changes when employment changes",
    ),
    Concept(
        "physical-security",
        ["physical security", "physical access", "facility access", "security zone",
         "secure area", "physical perimeter", "access logs"],
        why="publishers describe both facility protection and the authorisation and monitoring of entry",
    ),
    Concept(
        "asset-and-change-management",
        ["asset inventory", "enterprise asset inventory", "software inventory",
         "system component inventory", "configuration baseline", "configuration management",
         "change management", "configuration change control"],
        why="the control chain runs from knowing assets through secure baselines to authorised change",
    ),
    Concept(
        "network-architecture",
        ["network architecture", "network segmentation", "network segregation",
         "security zone", "boundary protection", "network boundary", "managed interface",
         "demilitarized zone", "demilitarised zone"],
        why="ASD says segmentation and segregation while 800-53 says managed interfaces and boundary protection",
    ),
    Concept(
        "security-awareness",
        ["security awareness", "cybersecurity awareness", "cyber security awareness",
         "literacy training", "role-based training", "role specific training",
         "security culture", "workforce training"],
        why="the same workforce outcome is labelled awareness, literacy and role-based training",
    ),
    Concept(
        "operational-technology",
        ["operational technology", "ot network", "ot system", "ot asset", "it and ot",
         "industrial control system", "scada", "field device"],
        why="the subject is usually abbreviated to OT and is expressed through assets, networks and operational playbooks",
    ),
]

CONCEPTS_BY_KEY = {c.key: c for c in CONCEPTS}


def concepts_for(text: str) -> List[Concept]:
    """Which concepts a piece of text is about, by whole-phrase match on stems."""
    stems = normalise_text(text)
    joined = " " + " ".join(stems) + " "
    out = []
    for concept in CONCEPTS:
        for phrase_stems in concept.stems:
            if not phrase_stems:
                continue
            needle = " " + " ".join(phrase_stems) + " "
            if needle in joined:
                out.append(concept)
                break
    return out


def concepts_in(text: str) -> List[Concept]:
    """Which concepts a piece of text is about, judged by control-side phrases.

    `concepts_for` answers the query-side question, where naming one Essential Eight
    strategy has to reach the group. Asking that of two arbitrary texts makes the group
    fire on both and declares almost any two security documents to share a subject.
    """
    stems = normalise_text(text)
    joined = " " + " ".join(stems) + " "
    out = []
    for concept in CONCEPTS:
        for phrase_stems in concept.control_stems:
            if not phrase_stems:
                continue
            if " " + " ".join(phrase_stems) + " " in joined:
                out.append(concept)
                break
    return out


def excluded_span(text: str, concept: Concept) -> bool:
    """Whether every occurrence sits inside a phrase the concept excludes."""
    if not concept.excluding:
        return False
    lowered = " ".join(normalise_text(text))
    for phrase in concept.excluding:
        needle = " ".join(normalise_text(phrase))
        if needle and needle in lowered:
            return True
    return False


# --------------------------------------------------------------------------
# Query preparation
# --------------------------------------------------------------------------


class PreparedQuery:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.tokens = tokenise(raw)
        self.stems = [normalise_token(t) for t in self.tokens]
        self.alias_stems = [
            normalise_token(t) for t in expand_aliases(self.tokens)
        ]
        self.concepts = concepts_for(raw)
        self.concept_stems: List[str] = []
        seen: Set[str] = set(self.stems)
        for concept in self.concepts:
            for phrase_stems in concept.stems:
                for s in phrase_stems:
                    if s not in seen:
                        seen.add(s)
                        self.concept_stems.append(s)

    @property
    def all_stems(self) -> List[str]:
        out: List[str] = []
        for s in list(self.stems) + list(self.alias_stems) + list(self.concept_stems):
            if s and s not in out:
                out.append(s)
        return out

    def explain(self) -> str:
        parts = ["query terms: %s" % ", ".join(sorted(set(self.stems)))]
        extra = sorted(set(self.alias_stems) - set(self.stems))
        if extra:
            parts.append("from abbreviations: %s" % ", ".join(extra))
        if self.concepts:
            parts.append(
                "concepts: %s" % ", ".join(c.key for c in self.concepts)
            )
        return "; ".join(parts)


def prepare(query: str) -> PreparedQuery:
    return PreparedQuery(query)


# --------------------------------------------------------------------------
# Naming a framework is not searching for a word
# --------------------------------------------------------------------------

# Typing ISM is a request for the Information Security Manual. Scored as a word it
# returned SP 800-88, which abbreviates information storage media the same way, and the
# ISM's own controls never use the abbreviation in their text at all. The same held for
# SOCI, CIRMP and OAG: the name of a document is not a term in it.
NAMED_SETS: Dict[str, Tuple[str, Optional[str], str]] = {
    "ism": ("ism", None, "the Information Security Manual"),
    "acsc": ("ism", None, "the Information Security Manual"),
    "asd": ("ism", None, "the Information Security Manual"),
    "pspf": ("pspf", None, "the Protective Security Policy Framework"),
    "soci": ("soci-act", None, "the SOCI Act"),
    "cirmp": ("cirmp-rules", None, "the CIRMP Rules"),
    "csf": ("csf", None, "the NIST Cybersecurity Framework"),
    "oag": ("oag-wa", None, "the OAG WA better practice guides"),
    "aescsf": ("aescsf", None, "the AESCSF"),
    "ztmm": ("ztmm", None, "the CISA Zero Trust Maturity Model"),
    "zero trust maturity model": ("ztmm", None, "the CISA Zero Trust Maturity Model"),
    # The document's name minus its last word. No other document in the corpus is called
    # this, and the rows of the model never say 'zero trust' themselves — each one
    # describes a stage — so a topical query for it reached the model at 0.119 against an
    # absolute floor of 0.12 and returned one PSPF requirement instead.
    "zero trust maturity": ("ztmm", None, "the CISA Zero Trust Maturity Model"),
    "c2m2": ("c2m2", None, "the Cybersecurity Capability Maturity Model"),
    "cybersecurity capability maturity model": (
        "c2m2",
        None,
        "the Cybersecurity Capability Maturity Model",
    ),
    "e8": ("ism", "essential_eight_maturity", "the Essential Eight maturity controls"),
    "essential eight": (
        "ism",
        "essential_eight_maturity",
        "the Essential Eight maturity controls",
    ),
}


def named_set(query: str) -> Optional[Tuple[str, Optional[str], str]]:
    """Whether the whole query is the name of a framework or a published tag."""
    key = " ".join(t for t in tokenise(query))
    return NAMED_SETS.get(key)
