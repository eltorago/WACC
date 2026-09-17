"""Numbers a publisher states, and what those numbers govern.

A number without its subject is not comparable to anything. The SOCI Act says 48 hours
in nineteen places and almost all of them are about a Ministerial authorisation given
orally, not about notifying an incident; the ISM says 12 hours about a session lock and
48 hours about patching; the WA CSP says 24 hours in four places meaning four different
things. So every threshold carries the clause it came out of, and comparison is only ever
offered within a subject the caller has already established.

Three things here exist because getting them wrong inverts a requirement.

A negation flips the bound and is never optional. SOCI s 18AA(3) says a period 'must not
be shorter than 28 days', which is a minimum of 28 days. Read as an upper bound it turns
a floor into a ceiling.

A cadence is a maximum interval. 'Reviewed at least every 24 months' is a lower bound on
frequency and an upper bound on the gap, and the gap is what a comparison is about.

Calendar units are not exact. Hours, days and weeks convert exactly; a month and a year
do not, so any comparison that crosses that line is marked approximate rather than
quietly asserting that 24 months is 17,520 hours.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

# Canonical units per dimension. A password of 15 characters and a key of 112 bits are
# both 'lengths' in English and are not the same quantity, so they are separate
# dimensions and never compared.
TIME = "time"
BITS = "bits"
CHARACTERS = "characters"

_EXACT_HOURS: Dict[str, float] = {
    "second": 1.0 / 3600,
    "minute": 1.0 / 60,
    "hour": 1.0,
    "day": 24.0,
    "week": 168.0,
}
# Stated conventions, applied openly, and every comparison that uses one says so.
_CALENDAR_HOURS: Dict[str, float] = {
    "month": 30 * 24.0,
    "year": 365 * 24.0,
}

_WORD_NUMBERS: Dict[str, float] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "twenty-four": 24, "thirty": 30, "sixty": 60, "ninety": 90,
}

_UNIT_WORDS = (
    "seconds", "second", "minutes", "minute", "hours", "hour", "days", "day",
    "weeks", "week", "months", "month", "years", "year", "bits", "bit",
    "characters", "character",
)

_NUMBER = r"(?:\d[\d,]*(?:\.\d+)?|%s)" % "|".join(
    sorted(_WORD_NUMBERS, key=len, reverse=True)
)
_QUANTITY = re.compile(
    r"(?<![\w.-])(%s)\s*(%s)\b" % (_NUMBER, "|".join(_UNIT_WORDS)), re.I
)

AT_MOST = "at most"
AT_LEAST = "at least"
EXACTLY = "exactly"
UNSTATED = "unstated"

# Read right to left from the number; only the phrase nearest it governs. The third
# column says whether the phrase already contains its own negative. 'Not set to greater
# than 1440 minutes' is a ceiling, and applying the negation a second time on top of the
# phrase turned that ceiling into a floor — the PMK caching period came out as a minimum.
_BOUNDS: Sequence[Tuple[str, str, bool]] = (
    ("at regular intervals no more than", AT_MOST, True),
    ("not set to greater than", AT_MOST, True),
    ("no greater than", AT_MOST, True),
    ("not longer than", AT_MOST, True),
    ("no later than", AT_MOST, True),
    ("not later than", AT_MOST, True),
    ("must not exceed", AT_MOST, True),
    ("not more than", AT_MOST, True),
    ("no more than", AT_MOST, True),
    ("no less than", AT_LEAST, True),
    ("not less than", AT_LEAST, True),
    ("less than", AT_MOST, False),
    ("shorter than", AT_MOST, False),
    ("a maximum of", AT_MOST, False),
    ("maximum of", AT_MOST, False),
    ("up to", AT_MOST, False),
    ("within", AT_MOST, False),
    ("after", AT_MOST, False),
    ("≤", AT_MOST, False),
    ("<=", AT_MOST, False),
    ("<", AT_MOST, False),
    ("at least every", AT_LEAST, False),
    ("a minimum of", AT_LEAST, False),
    ("minimum of", AT_LEAST, False),
    ("greater than", AT_LEAST, False),
    ("longer than", AT_LEAST, False),
    ("more than", AT_LEAST, False),
    ("at least", AT_LEAST, False),
    ("exceeds", AT_LEAST, False),
    ("≥", AT_LEAST, False),
    (">=", AT_LEAST, False),
    (">", AT_LEAST, False),
    ("of", UNSTATED, False),
)

# 'at least every 24 months' is a floor on how often and a ceiling on the gap. The gap is
# what two frameworks are compared on, so the bound is flipped and the reason recorded.
_CADENCE = ("at least every", "at regular intervals no more than", "every")

_NEGATIONS = ("must not", "shall not", "may not", "is not", "are not", "not set to",
              "cannot", "never")

# A bound word that does not abut the number still governs it: 'a minimum notification
# period of one month' puts two words between 'minimum' and the quantity. Read as a
# fallback only, and the reading is marked so a renderer can say the bound came from a
# nearby word rather than from the words in front of the number.
_LOOSE_BOUNDS: Sequence[Tuple[str, str]] = (
    ("maximum", AT_MOST),
    ("no more than", AT_MOST),
    ("must not exceed", AT_MOST),
    ("minimum", AT_LEAST),
    ("at least", AT_LEAST),
)

# '24 hours per day, 7 days per week' is a rate, not a requirement about a quantity.
_RATE_FOLLOWS = re.compile(r"^\s*(per|every|a|each)\s+(hour|day|week|month|year)\b", re.I)

# SP 800-131A's approval tables classify algorithms by status. 'Key lengths < 112 bits;
# Disallowed' is the name of a category, not a requirement that keys be under 112 bits,
# and read as one it contradicted every ISM minimum in the corpus.
_STATUS_WORDS = (
    "disallowed", "deprecated", "legacy use", "acceptable", "approval status",
    "restricted", "no longer approved",
)

_LOOKBACK = 52


@dataclass
class Threshold:
    value: float
    unit: str
    dimension: str
    bound: str
    subject: str
    quote: str
    control_uid: str
    negated: bool = False
    cadence: bool = False
    bound_inferred: bool = False
    restates: bool = False
    approximate: bool = False
    classifies: bool = False
    canonical: Optional[float] = None

    def describe(self) -> str:
        parts = [self.bound, _number(self.value), self.unit + ("s" if self.value != 1 else "")]
        if self.cadence:
            parts.append("between occurrences")
        if self.negated:
            parts.append("(stated as a negation, so the bound is flipped)")
        if self.bound_inferred:
            parts.append("(bound read from a nearby word, not from the words in front)")
        if self.approximate:
            parts.append("(calendar unit, so any comparison is approximate)")
        if self.classifies:
            parts.append("(a table category, not a requirement)")
        return " ".join(parts)


@dataclass
class Comparison:
    """What a set of thresholds on one subject actually says."""

    dimension: str
    thresholds: List[Threshold]
    strictest: Optional[Threshold] = None
    loosest: Optional[Threshold] = None
    approximate: bool = False
    incomparable: List[Threshold] = field(default_factory=list)
    note: str = ""

    @property
    def disagrees(self) -> bool:
        """Whether the frameworks state different numbers, which is not yet a conflict."""
        values = {
            (t.bound, round(t.canonical, 6))
            for t in self.thresholds
            if t.canonical is not None
        }
        return len(values) > 1


def _number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else ("%g" % value)


def _unit_key(word: str) -> str:
    word = word.lower()
    return word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _dimension(unit: str) -> Optional[str]:
    if unit in _EXACT_HOURS or unit in _CALENDAR_HOURS:
        return TIME
    if unit == "bit":
        return BITS
    if unit == "character":
        return CHARACTERS
    return None


def _to_number(raw: str) -> Optional[float]:
    token = raw.strip().lower().replace(",", "")
    if token in _WORD_NUMBERS:
        return float(_WORD_NUMBERS[token])
    try:
        return float(token)
    except ValueError:
        return None


def _canonical(value: float, unit: str) -> Tuple[Optional[float], bool]:
    if unit in _EXACT_HOURS:
        return value * _EXACT_HOURS[unit], False
    if unit in _CALENDAR_HOURS:
        return value * _CALENDAR_HOURS[unit], True
    if unit in ("bit", "character"):
        return value, False
    return None, False


# A flattened bullet list has no sentence punctuation between its items. Without the
# bullet as a boundary, an ISM control's SSH settings came back as one clause, and a
# 60-second login timeout was read as being about log retention because another bullet in
# the same span mentioned logging.
_CLAUSE_BREAKS = (". ", "; ", ": ", "\n", " - ", " • ", " — ")


def _clause(text: str, start: int, end: int) -> str:
    """The clause the number sits in, which is what it governs."""
    left = max([text.rfind(b, 0, start) + len(b) - 1 for b in _CLAUSE_BREAKS] + [-1])
    right_candidates = [i for i in (text.find(b, end) for b in _CLAUSE_BREAKS) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return " ".join(text[left + 1 : right].split()).strip(" .;:-—")


def _read_bound(before: str) -> Tuple[str, bool, bool, bool]:
    """Bound, negation and cadence, read from the words in front of the number."""
    window = " ".join(before.lower().split())
    bound = UNSTATED
    matched_at = -1
    self_negating = False
    best_start = len(window) + 1
    for phrase, sense, carries_its_own in _BOUNDS:
        position = window.rfind(phrase)
        if position == -1:
            continue
        if position + len(phrase) < len(window) - 2:
            # Only a phrase that runs up to the number governs it.
            continue
        # Among those, the longest wins, which is the one starting earliest. Taking the
        # nearest instead read 'no more than 60 seconds' as 'more than 60 seconds' and
        # turned an ISM login timeout ceiling into a floor.
        if position < best_start:
            best_start = position
            matched_at = position
            bound = sense
            self_negating = carries_its_own
    cadence = any(window.rstrip().endswith(c) for c in _CADENCE)

    tail = window[max(0, matched_at - 24) : matched_at] if matched_at >= 0 else window[-24:]
    negated = (not self_negating) and any(n in tail for n in _NEGATIONS)
    if negated and bound in (AT_MOST, AT_LEAST):
        # 'must not be shorter than 28 days' is a minimum of 28 days. Flipping is the
        # whole point; leaving the bound alone turns a floor into a ceiling.
        bound = AT_LEAST if bound is AT_MOST else AT_MOST
    if cadence:
        bound = AT_MOST

    inferred = False
    if bound is UNSTATED:
        nearest = -1
        for phrase, sense in _LOOSE_BOUNDS:
            position = window.rfind(phrase)
            if position > nearest:
                nearest = position
                bound = sense
        inferred = bound is not UNSTATED
    return bound, negated, cadence, inferred


def extract(text: str, control_uid: str = "") -> List[Threshold]:
    """Every stated quantity in one piece of text, with what it governs."""
    if not text:
        return []
    flat = text.replace("\n", " ")
    # Read off the whole row, not the clause. Narrowing the clause to 'Key lengths < 112
    # bits' correctly separated the quantity from its neighbours and separated it from
    # the word 'Disallowed' that says the row is a category.
    classifies = _is_classification(flat)
    out: List[Threshold] = []
    for match in _QUANTITY.finditer(flat):
        value = _to_number(match.group(1))
        if value is None:
            continue
        unit = _unit_key(match.group(2))
        dimension = _dimension(unit)
        if dimension is None:
            continue
        if _RATE_FOLLOWS.match(flat[match.end() : match.end() + 12]):
            # '24 hours per day' states a rate, not a bound on a quantity.
            continue
        before = flat[max(0, match.start() - _LOOKBACK) : match.start()]
        bound, negated, cadence, inferred = _read_bound(before)
        canonical, approximate = _canonical(value, unit)

        # 'less than 24 hours (86400 seconds)' states one quantity twice. The second is a
        # restatement, not a second requirement, and counting it produced two thresholds
        # where the publisher stated one.
        restates = bool(out) and _is_restatement(flat, out[-1], match)

        out.append(
            Threshold(
                value=value,
                unit=unit,
                dimension=dimension,
                bound=bound,
                subject=_clause(flat, match.start(), match.end()),
                quote=" ".join(flat[max(0, match.start() - 30) : match.end() + 4].split()),
                control_uid=control_uid,
                negated=negated,
                cadence=cadence,
                bound_inferred=inferred,
                restates=restates,
                classifies=classifies,
                approximate=approximate,
                canonical=canonical,
            )
        )
    return out


def _is_classification(clause: str) -> bool:
    lowered = clause.lower()
    return any(word in lowered for word in _STATUS_WORDS)


def _is_restatement(text: str, previous: Threshold, match) -> bool:
    gap = text[: match.start()]
    opened = gap.rfind("(")
    closed = gap.rfind(")")
    if opened == -1 or opened < closed:
        return False
    between = text[opened:match.start()]
    return len(between) <= 24 and previous.dimension == _dimension(
        _unit_key(match.group(2))
    )


def stated_by(control) -> List[Threshold]:
    """Thresholds a control states, restatements dropped."""
    text = ((control.title or "") + ". " + (control.text or "")).strip(". ")
    return [t for t in extract(text, control.uid) if not t.restates]


def compare(thresholds: Sequence[Threshold]) -> List[Comparison]:
    """Group by dimension and say what the group states. It never says who is right.

    Two frameworks stating different numbers for the same subject is a disagreement to
    report, not a conflict to resolve. Which one binds a particular entity depends on
    which documents apply to it, and that is not a question a crosswalk can answer.
    """
    groups: Dict[str, List[Threshold]] = {}
    for threshold in thresholds:
        if threshold.canonical is None:
            continue
        groups.setdefault(threshold.dimension, []).append(threshold)

    out: List[Comparison] = []
    for dimension, group in sorted(groups.items()):
        usable = [t for t in group if t.bound in (AT_MOST, AT_LEAST, EXACTLY)]
        unstated = [t for t in group if t.bound is UNSTATED]
        approximate = any(t.approximate for t in group)
        comparison = Comparison(
            dimension=dimension,
            thresholds=group,
            approximate=approximate,
            incomparable=unstated,
        )
        if usable:
            # Strictest means most demanding, which depends on the bound: the smallest
            # ceiling, or the largest floor. Mixing the two into one ordering is how a
            # deadline and a minimum key length end up compared to each other.
            ceilings = [t for t in usable if t.bound is AT_MOST]
            floors = [t for t in usable if t.bound is AT_LEAST]
            if ceilings and not floors:
                comparison.strictest = min(ceilings, key=lambda t: t.canonical)
                comparison.loosest = max(ceilings, key=lambda t: t.canonical)
            elif floors and not ceilings:
                comparison.strictest = max(floors, key=lambda t: t.canonical)
                comparison.loosest = min(floors, key=lambda t: t.canonical)
            else:
                comparison.note = (
                    "this set mixes ceilings and floors, so there is no single strictest "
                    "value; they are listed as stated"
                )
        if unstated:
            extra = (
                "%d of these state a quantity without saying whether it is a maximum or "
                "a minimum, so they are listed and not ranked" % len(unstated)
            )
            comparison.note = (comparison.note + ". " + extra).strip(". ")
        if approximate:
            extra = (
                "a month is read as 30 days and a year as 365, so any comparison "
                "crossing those units is approximate"
            )
            comparison.note = (comparison.note + ". " + extra).strip(". ")
        out.append(comparison)
    return out
