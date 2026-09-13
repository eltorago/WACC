"""Marking the words a control was returned for, without letting publisher text become markup.

A reader looking at twenty controls across six frameworks is asking one question of each:
why is this here? Marking the matched words answers it on the page instead of in a
separate explanation, which is the whole reason scoring is in Python rather than left to
FTS5 ranking.

The order of the two operations is the security property and it only works one way. Escape
first and the escaped text no longer lines up with the offsets the matcher found; mark
first and a control containing a less-than sign has had markup inserted into it before
anything escaped it. So neither is done to the whole string. The text is cut into spans at
token boundaries found in the raw text, every span is escaped on its own, and the marks are
the only unescaped characters this module ever emits.

Matching is on stems, not on the literal word. A query for patching has to mark 'patched'
and 'patches', because a highlighter that marks only the typed word tells the reader the
control matched on something it did not.

Two strengths, because the words come from two places. What the person typed, and spellings
of it, are marked plainly. The words a concept added on their behalf are marked faintly:
'patch applications' expands to twenty-five stems including 'system', 'security' and
'management', and marking those at full strength marks most of every control on the page,
which tells the reader nothing about why any one of them is there.
"""

import html as _html
import re
from typing import Iterable, List, Sequence, Set

from ..terms import normalise_token

# Case-insensitive, and the same shape as the tokeniser in terms.py: letters and digits,
# with an apostrophe allowed inside a word so "entity's" is one token rather than two.
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)*")

# A stem this short marks half the page. 'is', 'an' and 'or' carry no information about
# why a control was returned, and a page where everything is marked says nothing.
MIN_MARKED_STEM = 3


def wanted_stems(stems: Iterable[str]) -> Set[str]:
    """The stems worth marking, which is not every stem the search used."""
    return {s for s in stems if s and len(s) >= MIN_MARKED_STEM}


def mark(text: str, stems: Sequence[str], widened: Sequence[str] = ()) -> str:
    """HTML-escaped text with matched words wrapped in <mark>.

    `stems` is what the person typed and spellings of it. `widened` is what a concept
    added, marked faintly and never at the expense of a typed word: a stem in both sets
    is a typed word.

    Returns escaped markup. The caller must not escape the result again and must not pass
    text that has already been escaped, or the ampersands in the entities become tokens.
    """
    if not text:
        return ""
    typed = wanted_stems(stems)
    wide = wanted_stems(widened) - typed
    if not typed and not wide:
        return _html.escape(text, quote=True)

    out: List[str] = []
    cursor = 0
    for found in _WORD.finditer(text):
        stem = normalise_token(found.group(0))
        if stem in typed:
            css = "mark"
        elif stem in wide:
            css = "mark wide"
        else:
            continue
        out.append(_html.escape(text[cursor:found.start()], quote=True))
        out.append(
            '<mark class="%s">%s</mark>' % (css, _html.escape(found.group(0), quote=True))
        )
        cursor = found.end()
    out.append(_html.escape(text[cursor:], quote=True))
    return "".join(out)


def marked_count(text: str, stems: Sequence[str]) -> int:
    """How many words would be marked. Used by the tests, and by nothing that renders."""
    wanted = wanted_stems(stems)
    if not wanted:
        return 0
    return sum(
        1 for found in _WORD.finditer(text or "")
        if normalise_token(found.group(0)) in wanted
    )
