"""Round-trip every stored control back to the document it came from.

Extraction tooling. Not part of the shipped package, and not part of the test suite —
it needs the source documents and pdfplumber, and the work machine has neither.

The suite checks structure, licensing, retrieval and behaviour. None of that asks whether
the text of a control is the publisher's text. Reading SP 800-57 by hand found five rows
of one table stored under another table's caption and five paragraphs of narrative stored
as suggested cryptoperiods, and nothing in 368 checks could have found either. This looks
for the same class of defect everywhere at once.

The method is a measurement, not a verdict. A control's text is normalised and looked for
in the normalised text of its source document.

    verbatim   every word is there, in order
    near       almost every word is there, in order
    partial    some of it is there, and the share is reported
    absent     no run of it is there at all, which is a fabrication or a wrong source

Contiguity is the wrong test and calibrating on a known-good framework is what showed it.
C2M2's practices came back 55 partial out of 356 against an extractor already checked
against the document's own count of 356. The document is why. A maturity marker sits in
the left margin between the first and second line of the practice it opens, so the page
reads "...are inventoried, at least MIL1 in an ad hoc manner" and a contiguous match
fails on text that is entirely present. Footnote digits, running headers and sidebars all
do the same thing somewhere.

So the measure is order-preserving word coverage with a small tolerance for what the page
inserts. A control's words are matched in sequence against the document's, skipping up to
a few intruding tokens between them. Text that is really there scores 1.0 whatever the
page has put through the middle of it; text that is not scores near zero.

Normalisation folds case, whitespace, quotes and dashes on both sides, because a PDF
writes ’ and — where a docx writes ' and -, and a difference of typography is not a
difference of text.

What this cannot do is check a control against a document nobody has. Frameworks whose
source is absent are named and skipped rather than counted as clean.

Nor can it check a document whose text cannot be read in order. CISA's Zero Trust
Maturity Model keeps its content in tables that pdfplumber reports as nine columns where
there are five, which is why its own extractor reads word positions instead. Running a
linear haystack against it reports all forty functions as absent, and every one of them
is present. That is the instrument failing, not the corpus, so it is declared rather than
counted.
"""

import json
import os
import re
import sys
from typing import Dict, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from wacc.build import build, DOCUMENTS, RAW  # noqa: E402
from wacc.model import Control  # noqa: E402

CACHE = os.path.join(HERE, "data", "review", "cache")

# Frameworks whose source cannot be read as a linear stream of words, with the reason.
# Declared, because reporting forty false absences teaches a reader to ignore the column
# that matters.
UNREADABLE = {
    "ztmm": "the maturity tables do not survive linear extraction; its own parser reads "
            "word positions, and this check cannot",
}

ANCHOR = 4              # words used to find where in the document to start matching
MAX_SKIP = 8            # tokens the page may insert between two words of a control
NEAR = 0.97             # coverage at or above this, short of everything, is near
PARTIAL = 0.50          # below this, with an anchor, is still partial rather than absent
ANCHORS_TRIED = 12      # a common phrase can occur many times; try the first few
ANCHOR_PHRASES = 4      # and try more than one phrase, in case one straddles an insertion

_FOLD = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    " ": " ", "•": " ", "ﬁ": "fi", "ﬂ": "fl",
}
_FOLD_RE = re.compile("|".join(map(re.escape, _FOLD)))


def normalise(text: str) -> str:
    text = _FOLD_RE.sub(lambda m: _FOLD[m.group(0)], text or "")
    return " ".join(text.lower().split())


class Haystack:
    """One source document as a word list, with an index from opening phrases to positions.

    The index is what keeps this fast enough to run over five thousand controls: without
    an anchor every control would be scanned against every position in a document of tens
    of thousands of words.
    """

    def __init__(self, text: str) -> None:
        self.text = text
        self.words = text.split()
        self.index: Dict[str, List[int]] = {}
        for position in range(len(self.words) - ANCHOR + 1):
            key = " ".join(self.words[position:position + ANCHOR])
            self.index.setdefault(key, []).append(position)

    def anchors(self, needle: Sequence[str]) -> List[Tuple[int, int]]:
        """Where this text sits in the document, from its least common phrases.

        Three problems, all real on C2M2, and each one broke a different first attempt.

        Anchoring on the opening words fails on a document that repeats a stock phrase:
        "assets that are important to the delivery of the function" occurs dozens of
        times, so the first twelve hits were the wrong occurrence and practices that are
        in the document verbatim came back at 50 per cent.

        Anchoring on the single rarest phrase fails when that phrase straddles something
        the page inserted. The ten management-activity practices differ only in the domain
        name at the end, so the rarest phrase is the one containing it — and the maturity
        marker sits between "the" and the domain name, so that phrase does not occur in
        the document at all and the anchors found were all the wrong practice.

        So several of the least common phrases are offered, and the caller takes the best
        result across them. One of them will be clear of whatever the page inserted.
        """
        candidates: List[Tuple[int, int]] = []
        limit = max(1, min(len(needle), 60) - ANCHOR + 1)
        for offset in range(limit):
            key = " ".join(needle[offset:offset + ANCHOR])
            found = self.index.get(key)
            if found:
                candidates.append((len(found), offset))
        if not candidates:
            return []
        candidates.sort()
        anchors: List[Tuple[int, int]] = []
        for _count, offset in candidates[:ANCHOR_PHRASES]:
            key = " ".join(needle[offset:offset + ANCHOR])
            for position in self.index[key][:ANCHORS_TRIED]:
                anchors.append((position, offset))
        return anchors

    def _walk(self, words: Sequence[str], start: int, step: int) -> Tuple[int, int]:
        """Match words one way from a position, skipping what the page inserted."""
        matched = 0
        inserted = 0
        position = start
        for word in words:
            for skip in range(MAX_SKIP + 1):
                probe = position + skip * step
                if 0 <= probe < len(self.words) and self.words[probe] == word:
                    matched += 1
                    inserted += skip
                    position = probe + step
                    break
            else:
                position += step
        return matched, inserted

    def coverage(self, needle: Sequence[str]) -> Tuple[float, bool]:
        """The share of the control's words found in order, and whether none were skipped.

        Returns 1.0 when every word is present in sequence, whatever the page has put
        between them. Both directions are walked from the anchor, so a control whose
        rarest phrase is at its end is measured as well as one whose rarest phrase opens
        it.
        """
        if not needle:
            return 1.0, True
        best = 0.0
        best_clean = False
        for position, offset in self.anchors(needle):
            ahead, inserted_ahead = self._walk(needle[offset:], position, 1)
            behind, inserted_behind = self._walk(
                list(reversed(needle[:offset])), position - 1, -1
            )
            share = (ahead + behind) / float(len(needle))
            clean = (inserted_ahead + inserted_behind) == 0
            if share > best or (share == best and clean and not best_clean):
                best, best_clean = share, clean
            if best >= 1.0 and best_clean:
                break
        return best, best_clean


# Where a loader legitimately assembles one control from several pieces of the document.
# A table row is cells joined with "; ", a ZTMM function is four stage descriptions with
# the stage names put in front of them, a composed fragment is a parent stem and its
# child. None of those is contiguous in the source and all of them are honest.
# Square brackets as well, because the 800-53 loader substitutes each OSCAL parameter's
# label into the prose — "Implement [dynamic privilege management capabilities]" is one
# sentence in the catalogue and a separate parameter object elsewhere in the same file.
_PIECES = re.compile(r";\s|\s-\s|\.\s|:\s|[\[\]]")
PIECE_MIN = 4           # a fragment shorter than this proves nothing either way
PIECE_SHARE = 0.5       # and the pieces together have to be most of the control


def _pieces(words: Sequence[str]) -> List[List[str]]:
    parts = [p.split() for p in _PIECES.split(" ".join(words))]
    return [p for p in parts if len(p) >= PIECE_MIN]


def classify(text: str, haystacks: Sequence["Haystack"]) -> Tuple[str, float]:
    wanted = normalise(text).split()
    if not wanted:
        return "empty", 1.0

    # A needle shorter than an anchor phrase cannot be anchored, and most of them are
    # headings — "Control Logical Access", "Each entity must:". Looked for whole.
    if len(wanted) < ANCHOR:
        phrase = " ".join(wanted)
        if any(phrase in haystack.text for haystack in haystacks):
            return "verbatim", 1.0
        return "absent", 0.0

    best = 0.0
    best_clean = False
    for haystack in haystacks:
        share, clean = haystack.coverage(wanted)
        if share > best or (share == best and clean and not best_clean):
            best, best_clean = share, clean
        if best >= 1.0:
            break
    if best >= 1.0:
        return "verbatim", 1.0

    # Not contiguous. Whether every piece of it is there is a different question, and for
    # an assembled control it is the right one.
    pieces = _pieces(wanted)
    substantial = sum(len(p) for p in pieces) >= PIECE_SHARE * len(wanted)
    if pieces and substantial:
        found = 0
        for piece in pieces:
            if len(piece) < ANCHOR:
                phrase = " ".join(piece)
                if any(phrase in haystack.text for haystack in haystacks):
                    found += 1
                continue
            if any(haystack.coverage(piece)[0] >= 1.0 for haystack in haystacks):
                found += 1
        share = found / float(len(pieces))
        if share >= 1.0:
            return "joined", 1.0
        best = max(best, share)

    if best >= NEAR:
        return "near", best
    if best >= PARTIAL:
        return "partial", best
    return "absent", best


# --------------------------------------------------------------------------
# Reading a source document, once
# --------------------------------------------------------------------------


def _cache_path(path: str) -> str:
    return os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(path)) + ".txt")


def source_text(path: str) -> Optional[str]:
    """Every word of a source document, in one string, cached between runs."""
    if not os.path.exists(path):
        return None
    cached = _cache_path(path)
    if os.path.exists(cached) and os.path.getmtime(cached) >= os.path.getmtime(path):
        with open(cached, encoding="utf-8") as handle:
            return handle.read()

    suffix = os.path.splitext(path)[1].lower()
    if suffix == ".pdf":
        import pdfplumber

        parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        text = normalise(" ".join(parts))
    elif suffix == ".docx":
        from wacc.io.docx import Document

        parts = []
        for block in Document(path).blocks():
            if getattr(block, "rows", None):
                for row in block.rows:
                    parts.extend(row)
            else:
                parts.append(block.text)
        text = normalise(" ".join(parts))
    elif suffix in (".xlsx", ".xlsm"):
        from wacc.io.xlsx import Workbook

        workbook = Workbook(path)
        parts = []
        for sheet in workbook.sheet_names:
            for row in workbook.rows(sheet):
                parts.extend(str(c) for c in row)
        text = normalise(" ".join(parts))
    elif suffix == ".json":
        with open(path, encoding="utf-8") as handle:
            text = normalise(_json_text(json.load(handle)))
    else:
        return None

    os.makedirs(CACHE, exist_ok=True)
    with open(cached, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text


def _json_text(node) -> str:
    if isinstance(node, dict):
        return " ".join(_json_text(v) for v in node.values())
    if isinstance(node, list):
        return " ".join(_json_text(v) for v in node)
    return str(node) if isinstance(node, str) else ""


# --------------------------------------------------------------------------
# Where a framework's text came from
# --------------------------------------------------------------------------


def _resolve(name: str) -> Optional[str]:
    """A source file named by a registry entry or an extract, found on disk."""
    if not name:
        return None
    for candidate in (
        os.path.join(RAW, name),
        os.path.join(DOCUMENTS, name),
        os.path.join(DOCUMENTS, os.path.basename(name)),
        os.path.join(RAW, os.path.basename(name)),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_dir(name: str) -> Optional[str]:
    for candidate in (
        os.path.join(RAW, name.rstrip("/")), os.path.join(DOCUMENTS, name.rstrip("/"))
    ):
        if os.path.isdir(candidate):
            return candidate
    return None


def _named_sources(node) -> List[str]:
    out: List[str] = []
    if isinstance(node, dict):
        value = node.get("source_file")
        if isinstance(value, str):
            out.append(value)
        for item in node.values():
            out.extend(_named_sources(item))
    elif isinstance(node, list):
        for item in node:
            out.extend(_named_sources(item))
    return out


def sources_for(framework, corpus_dir: str) -> List[str]:
    """Every file a framework's text could have come from.

    The extract knows better than the registry does. A framework built from two OAG
    reports records one source per guide, and checking both against one of them would
    report half the corpus as absent.
    """
    found: List[str] = []
    extract = os.path.join(corpus_dir, "%s.json" % framework.key)
    if os.path.exists(extract):
        with open(extract, encoding="utf-8") as handle:
            payload = json.load(handle)
        for name in _named_sources(payload):
            resolved = _resolve(name)
            if resolved and resolved not in found:
                found.append(resolved)
    resolved = _resolve(framework.source_file or "")
    if resolved and resolved not in found:
        found.append(resolved)
    if not found and framework.source_file:
        directory = _resolve_dir(framework.source_file)
        if directory:
            for name in sorted(os.listdir(directory)):
                path = os.path.join(directory, name)
                if os.path.isfile(path):
                    found.append(path)
    return found


_HAYSTACKS: Dict[int, "Haystack"] = {}


def _haystack(text: str) -> "Haystack":
    key = id(text)
    if key not in _HAYSTACKS:
        _HAYSTACKS[key] = Haystack(text)
    return _HAYSTACKS[key]


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = [a for a in argv if not a.startswith("-")]
    show = "--show" in argv

    corpus, _ = build(verbose=False)
    corpus_dir = os.path.join(HERE, "data", "corpus")

    print("round-trip: every stored control looked for in the document it came from\n")
    header = "%-16s %6s %8s %6s %6s %8s %7s   %s" % (
        "framework", "texts", "verbatim", "joined", "near", "partial", "absent", "source"
    )
    print(header)
    print("-" * len(header))

    worst: List[Tuple[str, Control, str, float]] = []
    skipped: List[Tuple[str, str]] = []
    totals = {"texts": 0, "verbatim": 0, "joined": 0, "near": 0, "partial": 0, "absent": 0}

    for framework in corpus.ordered_frameworks():
        if only and framework.key not in only:
            continue
        controls = [
            c for c in corpus.controls_for(framework.key)
            if (c.text or "").strip() and not c.attributes.get("structural")
        ]
        if not controls:
            continue
        if framework.key in UNREADABLE:
            skipped.append((framework.key, UNREADABLE[framework.key]))
            continue
        paths = sources_for(framework, corpus_dir)
        haystacks = []
        for path in paths:
            text = source_text(path)
            if text:
                haystacks.append(_haystack(text))
        if not haystacks:
            skipped.append((framework.key, "no source document on this machine"))
            continue

        counts = {"verbatim": 0, "joined": 0, "near": 0, "partial": 0, "absent": 0, "empty": 0}
        for control in controls:
            verdict, share = classify(control.text, haystacks)
            counts[verdict] = counts.get(verdict, 0) + 1
            if verdict in ("absent", "partial"):
                worst.append((framework.key, control, verdict, share))

        for key in totals:
            if key == "texts":
                totals[key] += len(controls)
            else:
                totals[key] += counts.get(key, 0)
        print(
            "%-16s %6d %8d %6d %6d %8d %7d   %s"
            % (
                framework.key, len(controls), counts["verbatim"], counts["joined"],
                counts["near"], counts["partial"], counts["absent"],
                ", ".join(os.path.basename(p) for p in paths)[:40],
            )
        )

    print("-" * len(header))
    print(
        "%-16s %6d %8d %6d %6d %8d %7d"
        % ("total", totals["texts"], totals["verbatim"], totals["joined"],
           totals["near"], totals["partial"], totals["absent"])
    )

    if skipped:
        print("\nnot checked, because the source is not on this machine:")
        for key, why in skipped:
            print("  %-16s %s" % (key, why))

    if worst:
        print("\n%d controls are not fully in their source. Worst first:" % len(worst))
        for key, control, verdict, share in sorted(worst, key=lambda w: w[3])[: 40 if show else 12]:
            print(
                "  %-8s %-22s %-8s %3d%%  %s"
                % (key, control.identifier[:22], verdict, round(share * 100),
                   " ".join((control.text or "").split())[:70])
            )
    return 1 if totals["absent"] else 0


if __name__ == "__main__":
    sys.exit(main())
