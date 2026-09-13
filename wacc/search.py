"""Topical search: FTS5 retrieves, Python scores.

Retrieval and ranking are deliberately separate. SQLite finds the candidates because it
is fast and it ships with Python; the score is computed here, in the open, so a result
can say why it came back. A ranked list nobody can interrogate is not usable in a
finding.

Everything indexed is normalised through wacc.terms first, so the index holds one
spelling and one inflection of each word. Queries go through the same funnel. Nothing in
this file folds a spelling or strips a suffix of its own.

Three things this file does not do, each because doing them produced a wrong answer.

It does not cap the candidate set. A LIMIT on an unordered FTS5 match takes rows in load
order, and load order is tier 4 first, so a 600-row cap answered every broad query out of
the ISM alone and never said so.

It does not strip separators out of a query term. Removing the hyphen from 'multi-factor'
produces 'multifactor', which is not in the index, so the term retrieved nothing while
the scorer went on treating it as matched.

It does not weight every word alike. Document frequency is computed at index time, in
Python, from the same stem lists the scorer reads, so a rare word outranks a word that
appears in half the corpus without a hand-maintained stop list to go stale.
"""

import math
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .model import Control, Corpus, Tier, order_controls_governance_first
from .terms import (
    Concept,
    PreparedQuery,
    STOPWORDS,
    alias_alternatives,
    content_stems,
    excluded_span,
    named_set,
    prepare,
)

# A relative threshold with no floor beneath it calls the best of a bad set a match.
ABSOLUTE_FLOOR = 0.12
RELATIVE_FLOOR = 0.25

# BM25 saturation constants, applied to term frequency only. k1 sets how fast a repeated
# word stops adding; b sets how much a long control is discounted for having more room to
# contain the word.
K1 = 1.2
B = 0.75

# Field multipliers on term frequency. A title is the publisher naming the subject; body
# text may only mention it in passing. Placeholder titles never reach here — the OSCAL
# loader drops 'Control: ism-1234' rather than store a title that is an identifier.
TF_BODY = 1.0
TF_TITLE = 2.0
TF_SECTION = 0.8

BONUS_ALL_TERMS = 0.12
BONUS_PHRASE = 0.20
PENALTY_STRUCTURAL = 0.15

# A concept match is the tool doing its job, not a tiebreak. CM-7(5) is titled
# 'Authorized Software - Allow-by-exception' and contains neither word of the query
# 'application control'; if the concept is only worth a small bonus it can never reach
# the literal matches, and the crosswalk fails at exactly the case it exists for. The
# discount is for the match being derived from the vocabulary rather than read off the
# page, and it is reported as such.
WEIGHT_CONCEPT = 0.8

# The gate on a weak match is a term count, not a fraction. A fraction punished the long
# natural-language question 'how quickly must a cyber security incident be reported',
# where every control covers a small share of six words, and threw away the SOCI
# notification provisions that are the answer. One term is only enough when that term
# carries most of the question.
MIN_TERMS_MATCHED = 2
MIN_SOLO_WEIGHT = 0.7

# A pasted control is a legitimate query and a 500-word one took nine seconds, because
# every word was scored against every candidate. The rarest terms carry the subject, so
# the query keeps those and drops the rest; the count is reported when it bites.
MAX_QUERY_TERMS = 24

# How many places are given to the strongest matches before the list turns into a survey.
#
# The first attempt admitted a framework to a governance-ordered first pass whenever its
# best match was within a fraction of the best overall. Measured across the plan's ten
# topics, the frameworks that demonstrably address a topic score between 1.00 and 0.27 of
# the best match, and the frameworks that demonstrably do not score between 0.72 and 0.33.
# Those ranges overlap, so no threshold on the score separates them, and any value picked
# either buried a framework that requires the thing or promoted one that does not.
#
# The score cannot make that distinction and is not asked to. The strongest matches lead,
# and below them the list becomes one entry per publisher in governance order, which is
# the question a crosswalk is asked: what does each of them require here. Deciding whether
# a framework covers a subject at all is the analysis layer's job, not the ranker's.
LEAD_BY_SCORE = 5

# Governance-first is an ordering rule, not a scoring rule. This nudge only separates
# controls that are otherwise level; it can never lift an off-topic statute above an
# on-topic catalogue control.
TIER_NUDGE = {
    Tier.STATUTE: 0.06,
    Tier.MANDATED_POLICY: 0.05,
    Tier.OUTCOME: 0.03,
    Tier.CATALOGUE: 0.02,
    Tier.SPECIFICATION: 0.0,
}


@dataclass
class Scored:
    control: Control
    score: float
    reasons: List[str] = field(default_factory=list)

    def explain(self) -> str:
        return "%.3f  %s" % (self.score, "; ".join(self.reasons))


@dataclass
class SearchResult:
    query: str
    prepared: PreparedQuery
    hits: List[Scored]
    considered: int
    floor: float
    note: Optional[str] = None

    @property
    def found_nothing(self) -> bool:
        return not self.hits

    def frameworks(self) -> List[str]:
        out: List[str] = []
        for hit in self.hits:
            if hit.control.framework_key not in out:
                out.append(hit.control.framework_key)
        return out


@dataclass
class QueryTerm:
    """One word the person typed, and every form that means the same thing.

    An alias expansion is an alternative spelling, not an extra requirement, so
    alternatives are ORed and the stems inside one alternative are ANDed.
    """

    label: str
    alternatives: List[List[str]]
    weight: float


@dataclass
class Fields:
    """One control's searchable text, already stemmed, with counts kept."""

    body: Dict[str, int]
    title: Dict[str, int]
    section: Dict[str, int]
    length: int
    joined_body: str

    def present(self, stem: str) -> bool:
        """Whether the control says this word.

        The section reference is excluded. It names where a control sits, not what it
        requires, and counting it let an OAG guide match 'reported' through a heading
        two levels above the text and answer a question about notification timeframes.
        The section still raises the weight of a term matched in the body or title.
        """
        return stem in self.body or stem in self.title

    def weighted_tf(self, stem: str) -> float:
        return (
            TF_BODY * self.body.get(stem, 0)
            + TF_TITLE * self.title.get(stem, 0)
            + TF_SECTION * self.section.get(stem, 0)
        )

    def where(self, stem: str) -> str:
        if stem in self.title:
            return "title"
        return "text"


class SearchIndex:
    def __init__(self, corpus: Corpus) -> None:
        self.corpus = corpus
        # check_same_thread=False with a lock, because the local server hands requests to
        # whatever thread it likes and a sqlite3 connection is otherwise bound to the
        # thread that made it. Every query here is milliseconds, so serialising them costs
        # nothing and removes a crash that only appears once the server is threaded.
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.fields: Dict[str, Fields] = {}
        self.doc_freq: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.total_docs = 0
        self.average_length = 1.0
        self._build()

    # -- build -------------------------------------------------------------

    def _build(self) -> None:
        self.db.execute(
            "CREATE VIRTUAL TABLE controls USING fts5("
            "uid UNINDEXED, body, title, section, tokenize='unicode61')"
        )
        rows = []
        total_length = 0
        for uid, control in self.corpus.controls.items():
            body = content_stems(control.text)
            title = content_stems(control.title or "")
            section = content_stems(control.section_ref or "")
            if not (body or title or section):
                continue
            fields = Fields(
                body=_counts(body),
                title=_counts(title),
                section=_counts(section),
                length=len(body) + len(title) + len(section),
                joined_body=" " + " ".join(body + title) + " ",
            )
            self.fields[uid] = fields
            total_length += fields.length
            for stem in set(body) | set(title) | set(section):
                self.doc_freq[stem] = self.doc_freq.get(stem, 0) + 1
            rows.append((uid, " ".join(body), " ".join(title), " ".join(section)))

        self.db.executemany(
            "INSERT INTO controls(uid, body, title, section) VALUES (?, ?, ?, ?)", rows
        )
        self.db.commit()
        self.indexed = len(rows)
        self.total_docs = len(rows)
        self.average_length = (total_length / float(self.total_docs)) if self.total_docs else 1.0
        for stem, df in self.doc_freq.items():
            self.idf[stem] = math.log(
                1.0 + (self.total_docs - df + 0.5) / (df + 0.5)
            )

    def weight_of(self, stem: str) -> float:
        """A term absent from the corpus is as rare as a term seen once, not free."""
        return self.idf.get(stem, math.log(1.0 + (self.total_docs + 0.5) / 1.5))

    # -- search ------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 25,
        apply_floor: bool = True,
        compose: bool = True,
    ) -> SearchResult:
        """Ranked results. apply_floor=False keeps everything that scored at all.

        The floor is what stops a weak match being presented as an answer, so it is on
        for anything a person reads. It is off for diagnosis, where the question is where
        a control ranked, and 'below the floor' and 'not found' are different answers.

        compose=False returns strict score order, which is what to read when the question
        is how the scorer ranked something rather than what the tool should show.
        """
        prepared = prepare(query)

        named = named_set(query)
        if named is not None:
            return self._named_result(query, prepared, named, limit)

        terms = [t for t in prepared.all_stems if t]
        if not terms:
            return SearchResult(
                query=query,
                prepared=prepared,
                hits=[],
                considered=0,
                floor=ABSOLUTE_FLOOR,
                note="the query contained no searchable term",
            )

        candidates = self._candidates(terms)
        # Derived once. Building the query's terms inside the per-control scorer meant
        # five hundred words were re-stemmed for each of four thousand candidates, and a
        # pasted control took nine seconds to search.
        query_terms = self._query_terms(prepared)
        scored: List[Scored] = []
        for uid in candidates:
            control = self.corpus.control(uid)
            if control is None:
                continue
            hit = self._score(control, prepared, query_terms)
            if hit is not None:
                scored.append(hit)

        if not scored:
            return SearchResult(
                query=query,
                prepared=prepared,
                hits=[],
                considered=len(candidates),
                floor=ABSOLUTE_FLOOR,
                note="nothing in the corpus is about this",
            )

        scored.sort(
            key=lambda s: (-s.score, s.control.framework_key, s.control.identifier_key)
        )
        best = scored[0].score
        floor = max(ABSOLUTE_FLOOR, best * RELATIVE_FLOOR)
        above = [s for s in scored if s.score >= floor] if apply_floor else scored
        kept = (self._compose(above, best) if compose else above)[:limit]

        note = None
        if not kept:
            note = (
                "the best match scored %.3f, below the absolute floor of %.2f, so "
                "nothing is reported" % (best, ABSOLUTE_FLOOR)
            )
        return SearchResult(
            query=query,
            prepared=prepared,
            hits=kept,
            considered=len(candidates),
            floor=floor,
            note=note,
        )

    def _compose(self, hits: List[Scored], best: float) -> List[Scored]:
        """Order the list the way the question was asked. Scores are not touched.

        Strict score order answered a multi-factor authentication query with twenty-five
        ISM controls and no sign that seven other frameworks require it too, which is the
        one thing the tool exists to show. So the strongest matches lead, and then every
        framework not yet represented contributes its best match in governance order.
        """
        if not hits:
            return hits
        out: List[Scored] = list(hits[:LEAD_BY_SCORE])
        taken: Set[str] = {hit.control.uid for hit in out}
        represented: Set[str] = {hit.control.framework_key for hit in out}

        remaining: Dict[str, List[Scored]] = {}
        for hit in hits[LEAD_BY_SCORE:]:
            if hit.control.framework_key in represented:
                continue
            remaining.setdefault(hit.control.framework_key, []).append(hit)

        leaders = [group[0] for group in remaining.values()]
        for control in order_controls_governance_first(
            self.corpus, [hit.control for hit in leaders]
        ):
            hit = remaining[control.framework_key][0]
            out.append(hit)
            taken.add(hit.control.uid)

        for hit in hits:
            if hit.control.uid not in taken:
                out.append(hit)
        return out

    def _named_result(
        self,
        query: str,
        prepared: PreparedQuery,
        named: Tuple[str, Optional[str], str],
        limit: int,
    ) -> SearchResult:
        """The query is the name of a document, so return the document.

        Nothing is scored here. A person who types ISM has asked which controls the ISM
        holds, and answering with a ranked list of controls that happen to contain the
        letters is a different question with a worse answer.
        """
        framework_key, tag, description = named
        controls = [
            control
            for control in self.corpus.controls.values()
            if control.framework_key == framework_key
            and (tag is None or control.publisher_tags.get(tag) or control.attributes.get(tag))
        ]
        ordered = order_controls_governance_first(self.corpus, controls)
        hits = [
            Scored(control=control, score=0.0, reasons=["named set: %s" % description])
            for control in ordered
        ]
        note = "%r names %s, so this lists it rather than searching for the word. %d controls%s." % (
            query.strip(),
            description,
            len(hits),
            "" if limit >= len(hits) else ", showing the first %d" % limit,
        )
        return SearchResult(
            query=query,
            prepared=prepared,
            hits=hits[:limit],
            considered=len(hits),
            floor=0.0,
            note=note,
        )

    # -- internals ---------------------------------------------------------

    def _candidates(self, terms: Sequence[str]) -> List[str]:
        """Every control mentioning any term. Precision is the scorer's job.

        No LIMIT. Scoring the whole match set costs milliseconds; taking the first n rows
        of an unordered match costs recall in a way that leaves no trace in the output.
        """
        clauses = []
        for term in terms:
            clause = _fts_clause(term)
            if clause and clause not in clauses:
                clauses.append(clause)
        if not clauses:
            return []
        match = " OR ".join(clauses)
        try:
            with self._lock:
                rows = self.db.execute(
                    "SELECT uid FROM controls WHERE controls MATCH ?", (match,)
                ).fetchall()
        except sqlite3.OperationalError:
            # A query the FTS5 parser rejects is a bad query, not a crash.
            return []
        return [r["uid"] for r in rows]

    def _score(
        self,
        control: Control,
        prepared: PreparedQuery,
        query_terms: Optional[Sequence["QueryTerm"]] = None,
    ) -> Optional[Scored]:
        fields = self.fields.get(control.uid)
        if fields is None:
            return None

        terms = self._query_terms(prepared) if query_terms is None else list(query_terms)
        concepts = [c for c in prepared.concepts]
        if not terms and not concepts:
            return None

        reasons: List[str] = []

        literal, coverage, matched = self._literal_score(terms, fields)
        conceptual, concept_notes = self._concept_score(control, concepts, fields)

        # max, not sum. A control carrying the literal phrase also carries the concept
        # phrase, and adding both scored the same evidence twice.
        subject = max(literal, WEIGHT_CONCEPT * conceptual)
        if subject <= 0:
            return None
        if conceptual <= 0 and len(matched) < MIN_TERMS_MATCHED:
            if not matched or coverage < MIN_SOLO_WEIGHT:
                # Mentioning one incidental word of the question is not answering it.
                return None

        score = subject
        if matched:
            reasons.append(
                "%d of %d query terms (%s)"
                % (
                    len(matched),
                    len(terms),
                    ", ".join(
                        "%s in %s, weight %.2f" % (label, where, weight)
                        for label, where, weight in matched
                    ),
                )
            )
        reasons.extend(concept_notes)

        if len(matched) == len(terms) and len(terms) > 1:
            score += BONUS_ALL_TERMS
            reasons.append("every query term present")

        if _phrase_present(prepared.stems, fields.joined_body):
            score += BONUS_PHRASE
            reasons.append("the query appears as a phrase")

        framework = self.corpus.frameworks.get(control.framework_key)
        if framework is not None and framework.tier is not None:
            nudge = TIER_NUDGE.get(framework.tier, 0.0)
            if nudge:
                score += nudge
                reasons.append("tier %d" % framework.tier.value)

        if control.attributes.get("structural"):
            score -= PENALTY_STRUCTURAL
            reasons.append("structural heading, not a requirement")

        return Scored(control=control, score=round(score, 4), reasons=reasons)

    # -- score parts -------------------------------------------------------

    def _query_terms(self, prepared: PreparedQuery) -> List["QueryTerm"]:
        """One entry per word the person typed, carrying its equivalent forms."""
        out: List[QueryTerm] = []
        seen: Set[str] = set()
        for token, forms in alias_alternatives(prepared.tokens):
            forms = [f for f in forms if f and not all(p in STOPWORDS for p in f)]
            if not forms:
                continue
            key = "|".join(" ".join(f) for f in forms)
            if key in seen:
                continue
            seen.add(key)
            weight = max(
                min(self.weight_of(stem) for stem in form) for form in forms
            )
            out.append(QueryTerm(label=token, alternatives=forms, weight=weight))
        if len(out) > MAX_QUERY_TERMS:
            out = sorted(out, key=lambda t: -t.weight)[:MAX_QUERY_TERMS]
        return out

    def _literal_score(
        self, terms: Sequence["QueryTerm"], fields: Fields
    ) -> Tuple[float, float, List[Tuple[str, str, float]]]:
        if not terms:
            return 0.0, 0.0, []
        total_weight = sum(t.weight for t in terms) or 1.0
        score = 0.0
        covered = 0.0
        matched: List[Tuple[str, str, float]] = []
        for term in terms:
            best_tf = 0.0
            best_form: Optional[List[str]] = None
            for form in term.alternatives:
                if not all(fields.present(stem) for stem in form):
                    continue
                tf = min(fields.weighted_tf(stem) for stem in form)
                if tf > best_tf:
                    best_tf, best_form = tf, form
            if best_form is None:
                continue
            share = term.weight / total_weight
            covered += share
            score += share * _saturate(best_tf, fields.length, self.average_length)
            matched.append((term.label, fields.where(best_form[0]), share))
        return score, covered, matched

    def _concept_score(
        self, control: Control, concepts: Sequence[Concept], fields: Fields
    ) -> Tuple[float, List[str]]:
        """A concept fires on a whole phrase, never on one of its words.

        Matching a concept's individual stems let 'authentication' alone assert the
        multi-factor concept, which put every password control in an MFA result.
        """
        if not concepts:
            return 0.0, []
        hits = 0
        notes: List[str] = []
        best = 0.0
        for concept in concepts:
            if excluded_span(control.text, concept):
                # Every occurrence sits inside a phrase this concept excludes.
                continue
            for phrase, phrase_stems in zip(concept.control_phrases, concept.control_stems):
                if not phrase_stems:
                    continue
                needle = " " + " ".join(phrase_stems) + " "
                occurrences = fields.joined_body.count(needle)
                if not occurrences:
                    continue
                hits += 1
                best = max(
                    best, _saturate(float(occurrences), fields.length, self.average_length)
                )
                notes.append("says '%s' (concept %s)" % (phrase, concept.key))
                break
        if not hits:
            return 0.0, []
        # The best concept, not the average. A query can name a subject and the group it
        # belongs to; a control that matches the subject has answered it, and dividing by
        # the number of concepts the query raised halved exactly those matches.
        return best, notes


def _counts(stems: Sequence[str]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for stem in stems:
        out[stem] = out.get(stem, 0) + 1
    return out


def _saturate(tf: float, length: int, average_length: float) -> float:
    """BM25 term weight, normalised to 0..1 so scores compare across queries."""
    if tf <= 0:
        return 0.0
    denominator = tf + K1 * (1.0 - B + B * (length / (average_length or 1.0)))
    return (tf * (K1 + 1.0)) / denominator / (K1 + 1.0)


def _fts_clause(term: str) -> str:
    """One query term as FTS5 syntax, with separators kept as token boundaries.

    unicode61 splits the indexed text on the hyphen in 'multi-factor', so the query has
    to split there too and ask for the two tokens adjacent. Collapsing them into
    'multifactor' asks for a token the index has never held.
    """
    parts = [p for p in re.split(r"[^a-z0-9]+", term.lower()) if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return '"%s"' % " ".join(parts)


def _phrase_present(query_stems: Sequence[str], joined_body: str) -> bool:
    stems = [s for s in query_stems if s]
    if len(stems) < 2:
        return False
    return " " + " ".join(stems) + " " in joined_body
