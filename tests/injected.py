"""The injected-regression matrix: what the suite would catch if the defect came back.

A green suite proves that nothing currently fails. It does not prove that anything is
being watched. Every case in tests/ names the defect it came from, and every one of those
was written after the tool got an answer wrong — but a case can decay into a check that
cannot fail, and nothing in a passing run says so.

So each defect is put back, one at a time, into a copy of the tree, and the suite that
was written for it is run against the broken copy. A defect the suite no longer catches
is reported as a gap, not quietly dropped. That is the difference between a regression
suite and a list of things that happen to be true.

Three things this harness insists on, each because the weaker version proves nothing.

The injection has to land. Every substitution must match its file exactly once. Zero
matches means the code moved and the entry now describes nothing; two means the entry is
ambiguous about which site it is breaking. Either way the matrix is stale and says so,
rather than reporting a defect as caught when it was never introduced.

The baseline has to be clean. A suite is run untouched first, and the FAIL lines it
already produces are subtracted. Otherwise an injection inherits credit for a failure
that was there before it.

The named case has to fire. Exit code alone is too weak — a suite can fail for a reason
that has nothing to do with the injection, which is a false pass for the case the matrix
claims to be exercising. Each entry names the case, and the run reports which cases
actually fired so the entry can be corrected when a case is renamed.

Not in tests/run_all.py by default. It runs the suites tens of times over and takes
minutes; the daily runner stays fast. run_all.py --injected includes it, and the summary
says when it was skipped, because a matrix nobody runs is worse than no matrix.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

HUNG = -999  # a suite that did not return inside SUITE_TIMEOUT

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _wrap(text: str, width: int, indent: str) -> List[str]:
    lines: List[str] = []
    current = indent
    for word in text.split():
        if len(current) + len(word) + 1 > width and current.strip():
            lines.append(current)
            current = indent + word
        else:
            current = (current + " " + word) if current.strip() else indent + word
    if current.strip():
        lines.append(current)
    return lines


@dataclass
class Injection:
    """One recorded defect, put back where it was.

    `edits` are (exact text, replacement) pairs applied to one file. `caught_by` names
    the cases that must fail — matched as substrings of the suite's own FAIL lines, so
    renaming a case breaks the entry loudly rather than silently widening it.
    """

    key: str
    defect: str
    was: str
    path: str
    edits: Sequence[Tuple[str, str]]
    suites: Sequence[str]
    caught_by: Sequence[str]
    note: str = ""


# The order is the build order: vocabulary, retrieval, structure, meaning, presentation,
# packaging. A defect low in the stack is worth reading first for the same reason the
# suite runs lowest-first.
MATRIX: List[Injection] = [

    # -- vocabulary --------------------------------------------------------

    Injection(
        key="iz-fold",
        defect="the -iz family is no longer folded to one root",
        was="the ISM writes 'sanitised' and NIST writes 'Media Sanitization'. Folding "
            "the spelling alone left sanitiz and sanitization apart, and ISM-1742 could "
            "not be reached from a query naming the NIST title",
        path="wacc/terms.py",
        edits=[("    return _fold_iz_family(lower)\n", "    return lower\n")],
        suites=["test_terms.py"],
        caught_by=["sanitised / sanitization"],
    ),
    Injection(
        key="ation-split",
        defect="'-ation' is no longer reduced to its verb",
        was="ASD writes 'Use MFA to authenticate privileged users'; a query for "
            "multi-factor authentication scored nothing against it",
        path="wacc/terms.py",
        edits=[("    for suffix in _ATION:\n", "    for suffix in ():\n")],
        suites=["test_terms.py"],
        caught_by=["authenticate / authentication"],
    ),
    Injection(
        key="silent-e",
        defect="the trailing e survives the inflection strip",
        was="the past tense of a verb ending in e adds d, so 'stored' became stor while "
            "'store' stayed whole and the two halves of one word never met",
        path="wacc/terms.py",
        edits=[(
            '    if root.endswith("e") and len(root) - 1 >= MIN_STEM_LENGTH:\n'
            "        return root[:-1]\n"
            "    return root\n",
            "    return root\n",
        )],
        suites=["test_terms.py"],
        caught_by=["store / stored"],
    ),
    Injection(
        key="es-plural",
        defect="'es' is stripped as a plural after any letter",
        was="stripping -es from 'privileges' gave privileg while 'privilege' kept its e, "
            "and the privileged-access concept could not fire on the query naming it",
        path="wacc/terms.py",
        edits=[(
            '        if suffix == "es" and not root.endswith(_SIBILANTS):\n',
            "        if False:\n",
        )],
        suites=["test_terms.py"],
        caught_by=["trustees and trust"],
        note="privilege/privileges no longer proves this: _drop_silent_e collapses that "
             "pair from the other direction, so the guard is invisible on it. Five words "
             "in the corpus do depend on it, all of them -ees — trustees, employees, "
             "licensees, committees, oversees — and without the guard trustees becomes "
             "trust, which is the word zero trust is about.",
    ),
    Injection(
        key="group-leak",
        defect="a group concept matches its member phrases inside controls",
        was="naming one Essential Eight strategy reached the other seven, so an "
            "application control query was answered with multi-factor authentication",
        path="wacc/terms.py",
        edits=[(
            "        self.control_phrases = [\n"
            "            p.lower() for p in (phrases if control_phrases is None else control_phrases)\n"
            "        ]\n",
            "        self.control_phrases = [p.lower() for p in phrases]\n",
        )],
        suites=["test_terms.py"],
        caught_by=["Essential Eight member phrases leak into controls"],
    ),
    Injection(
        key="question-words",
        defect="question words are search terms again",
        was="'how' matched the OAG heading 'Understand how accounts are used' and put "
            "account visibility in an incident-timeframe result",
        path="wacc/terms.py",
        edits=[(
            '    "how", "what", "who", "whom", "whose", "why", "quickly", "soon", "long", "many",\n'
            '    "much", "should", "shall", "need", "needs",\n',
            '    "whom", "whose",\n',
        )],
        suites=["test_terms.py"],
        caught_by=["'how' is being searched for"],
    ),

    # -- retrieval ---------------------------------------------------------

    Injection(
        key="prose-to-lookup",
        defect="prose enters the exact-identifier path",
        was="a query with no digit in it is not an identifier; running it through exact "
            "lookup invited a bare-token match and skipped topical search entirely",
        path="wacc/lookup.py",
        edits=[(
            "    if not _HAS_DIGIT.search(text):\n        return False\n",
            "    if False:\n        return False\n",
        )],
        suites=["test_identifier_lookup.py"],
        caught_by=["was treated as an identifier"],
    ),
    Injection(
        key="alias-beats-primary",
        defect="an alias hit is taken before a primary hit",
        was="typing '3.10' could be answered by something whose bare tail happens to be "
            "3.10 rather than by the control whose own identifier it is",
        path="wacc/lookup.py",
        edits=[(
            "        for form in forms:\n"
            "            if form in self.primary:\n"
            "                return list(self.primary[form]), form\n"
            "        for form in forms:\n"
            "            if form in self.alias:\n"
            "                return list(self.alias[form]), form\n",
            "        for form in forms:\n"
            "            if form in self.alias:\n"
            "                return list(self.alias[form]), form\n"
            "        for form in forms:\n"
            "            if form in self.primary:\n"
            "                return list(self.primary[form]), form\n",
        )],
        suites=["test_identifier_lookup.py"],
        caught_by=["expected cis-controls:3.10"],
    ),
    Injection(
        key="candidate-cap",
        defect="the FTS5 match set is capped at 600 rows",
        was="a LIMIT on an unordered match takes rows in load order, and load order is "
            "tier 4 first, so every broad query was answered out of the ISM alone and "
            "nothing in the output said so",
        path="wacc/search.py",
        edits=[(
            '                    "SELECT uid FROM controls WHERE controls MATCH ?", (match,)\n',
            '                    "SELECT uid FROM controls WHERE controls MATCH ? LIMIT 600",\n'
            "                    (match,),\n",
        )],
        suites=["test_topical_search.py"],
        caught_by=["witnesses absent from the results"],
    ),
    Injection(
        key="separator-strip",
        defect="the hyphen is part of a token again",
        was="'multi-factor' and 'multi factor' were different queries for one question, "
            "because SQLite's tokeniser splits at the hyphen whatever this module does",
        path="wacc/terms.py",
        edits=[(
            "_TOKEN = re.compile(r\"[a-z0-9]+(?:'[a-z0-9]+)*\")\n",
            "_TOKEN = re.compile(r\"[a-z0-9-]+(?:'[a-z0-9]+)*\")\n",
        )],
        suites=["test_terms.py", "test_topical_search.py"],
        caught_by=["'multi-factor' and 'multi factor' still differ"],
        note="the same defect injected at the search layer instead — collapsing the "
             "term inside _fts_clause — changes nothing, and that is not a hole. The "
             "query carries 'multi' and 'factor' as terms of their own, so the phrase "
             "clause adds no row the component terms do not already retrieve: measured "
             "at 0 of 244 controls lost on the MFA queries. The guard that holds this "
             "up now is the tokeniser, so that is where it is injected.",
    ),
    Injection(
        key="flat-idf",
        defect="every word weighs the same",
        was="without document frequency, a query's rare word counted no more than a word "
            "in half the corpus, and twenty-five results came back on two distinct scores",
        path="wacc/search.py",
        edits=[(
            '        """A term absent from the corpus is as rare as a term seen once, not free."""\n'
            "        return self.idf.get(stem, math.log(1.0 + (self.total_docs + 0.5) / 1.5))\n",
            "        return 1.0\n",
        )],
        suites=["test_topical_search.py"],
        caught_by=["carrying no more weight than the commonest one"],
    ),
    Injection(
        key="thread-bound",
        defect="the FTS5 connection is bound to the thread that made it",
        was="the local server hands requests to whatever thread it likes, so any "
            "concurrent search crashed",
        path="wacc/search.py",
        edits=[(
            '        self.db = sqlite3.connect(":memory:", check_same_thread=False)\n',
            '        self.db = sqlite3.connect(":memory:")\n',
        )],
        suites=["test_render.py"],
        caught_by=["eight concurrent searches all answer"],
    ),

    # -- structure ---------------------------------------------------------

    Injection(
        key="framework-reentry",
        defect="a chain re-enters a document it has already left",
        was="ISM-1683 reached the AESCSF by way of CIS 6.3 and came back into ISM-1504, "
            "which is a different ISM control and asserts nothing about the first",
        path="wacc/relate.py",
        edits=[(
            "            if relation.other.framework_key in visited_frameworks:\n"
            "                continue\n",
            "",
        )],
        suites=["test_relate.py"],
        caught_by=["no chain re-enters a document it has left"],
    ),
    Injection(
        key="objective-dot",
        defect="an objective heading must end its number with a full stop",
        was="C2M2's THREAT domain heads its third objective '3 Management Activities for "
            "the THREAT domain' with no stop. Requiring one merged its eleven practices "
            "into objective 2 and gave six of them identifiers that already existed",
        path="data/corpus/c2m2.json",
        edits=[(
            '"objective_number": 3,\n   "objective": "Management Activities for the THREAT domain",\n'
            '   "letter": "a",\n   "identifier": "THREAT-3a"',
            '"objective_number": 2,\n   "objective": "Respond to Threats and Share Threat Information",\n'
            '   "letter": "l",\n   "identifier": "THREAT-2l"',
        )],
        suites=["test_c2m2.py"],
        caught_by=["practice letters run a, b, c with no gaps"],
    ),
    Injection(
        key="mil-lost",
        defect="a practice carries no maturity indicator level",
        was="the marker sits in the left margin below the practice it opens and on some "
            "pages shares a baseline with it. Missing the shared-baseline dialect lost "
            "RISK-4a to RISK-4c and left RISK-4d and RISK-4e with no level, and the level "
            "is what s 8(4) and s 8A(3) each require a different one of",
        path="data/corpus/c2m2.json",
        edits=[('"identifier": "RISK-4d",\n   "mil": 3,', '"identifier": "RISK-4d",\n   "mil": null,')],
        suites=["test_c2m2.py"],
        caught_by=["every practice carries a maturity indicator level"],
    ),
    Injection(
        key="named-after-tier-one",
        defect="a framework named by a statutory table loads after the table is resolved",
        was="tier 1 resolves its framework tables against frameworks already in the "
            "corpus. C2M2 loaded with the other tier-3 addition, after the legislation, "
            "produced no links at all and nothing said so — the instrument simply "
            "appeared to name nothing",
        path="wacc/build.py",
        edits=[(
            '    c2m2_framework = corpus.frameworks.get("c2m2")\n'
            '    c2m2_path = os.path.join(CORPUS, "c2m2.json")\n'
            '    if c2m2_framework is not None:\n'
            '        if os.path.exists(c2m2_path):\n'
            '            report.record("c2m2", c2m2.load(corpus, c2m2_framework, c2m2_path, verbose))\n'
            '        else:\n'
            '            report.skip("c2m2", "extract not present; run tools/extract_c2m2.py")\n'
            '\n'
            '    # -- tier 2',
            '    # -- tier 2',
        )],
        suites=["test_c2m2.py"],
        caught_by=["both CIRMP framework tables incorporate C2M2"],
    ),
    Injection(
        key="edition-collapsed",
        defect="one entry matches two editions a table names separately",
        was="s 8(4) names the 2020-21 AESCSF Framework Core and s 8A(3) names the 2023 "
            "one. A single entry matching the phrase they share put the one workbook the "
            "corpus holds inside both obligations, and incorporation is the only link "
            "kind that carries a duty",
        path="wacc/loaders/legislation.py",
        edits=[(
            '    ("202021 AESCSF Framework Core", None,\n'
            '     "not loaded — this names the 2020-21 edition. The corpus holds the 2023 Framework "\n'
            '     "Core, which is the edition s 8A(3) names"),\n'
            '    ("2023 AESCSF Framework Core", "aescsf", "loaded"),\n',
            '    ("AESCSF Framework Core", "aescsf", "loaded"),\n',
        )],
        suites=["test_relate.py"],
        caught_by=["only the enhanced regime names the AESCSF edition"],
    ),
    Injection(
        key="condition-dropped",
        defect="a framework table's condition does not reach the link",
        was="CIRMP s 8(4) names the AESCSF at Security Profile 1 and s 8A(3) names it at "
            "Security Profile 2. Both links read 'named in the framework table of this "
            "provision', so the two regimes were indistinguishable in every chain, and "
            "for a maturity framework the profile is the obligation",
        path="wacc/loaders/legislation.py",
        edits=[(
            '        basis = "named in the framework table of this provision"\n'
            "        if condition:\n"
            '            basis = "%s \u2014 condition: %s" % (basis, condition)\n',
            '        basis = "named in the framework table of this provision"\n',
        )],
        suites=["test_relate.py"],
        caught_by=["state different conditions"],
    ),
    Injection(
        key="sibling-hop",
        defect="a chain descends after it has ascended",
        was="CIS 6.4 climbed to its parent control 6 and came back down to safeguard "
            "6.1, then used 6.1's mapping — which is what requires a sibling, not 6.4",
        path="wacc/relate.py",
        edits=[
            ("        if control.parent_uid and not descended:\n",
             "        if control.parent_uid:\n"),
            ("        if not ascended:\n            for child in self.children(control.uid):\n",
             "        if True:\n            for child in self.children(control.uid):\n"),
        ],
        suites=["test_relate.py"],
        caught_by=["no chain climbs to a parent and comes back down to a sibling"],
    ),

    # -- meaning -----------------------------------------------------------

    Injection(
        key="double-negation",
        defect="a self-negating bound phrase is negated a second time",
        was="'not set to greater than 1440 minutes' is a ceiling, and applying the "
            "negation on top of the phrase turned the PMK caching period into a minimum",
        path="wacc/thresholds.py",
        edits=[(
            "    negated = (not self_negating) and any(n in tail for n in _NEGATIONS)\n",
            "    negated = any(n in tail for n in _NEGATIONS)\n",
        )],
        suites=["test_analysis.py"],
        caught_by=["does not flip it"],
        note="the case that named this defect does not fail when the column is dropped, "
             "and that is honest rather than broken: two defences were added for one bug "
             "and the other one — reading the negation only from the words before the "
             "matched phrase — is what holds 'not set to greater than' up. No control in "
             "the corpus puts a negation immediately in front of a self-negating phrase, "
             "so the case that does fail uses a constructed wording and says so.",
    ),
    Injection(
        key="nearest-bound",
        defect="the bound phrase nearest the number wins instead of the longest",
        was="'no more than 60 seconds' was read as 'more than', which turned an ISM "
            "login timeout ceiling into a floor",
        path="wacc/thresholds.py",
        edits=[
            ("    best_start = len(window) + 1\n", "    best_start = -1\n"),
            ("        if position < best_start:\n", "        if position > best_start:\n"),
        ],
        suites=["test_analysis.py"],
        caught_by=["is a ceiling, not 'more than'"],
    ),
    Injection(
        key="table-category",
        defect="an approval table's category line is read as a requirement",
        was="SP 800-131A's 'Key lengths < 112 bits; Disallowed' names a category. Read "
            "as a requirement it contradicted every ISM minimum in the corpus — 27 "
            "conflicts, none of them real",
        path="wacc/thresholds.py",
        edits=[(
            "    return any(word in lowered for word in _STATUS_WORDS)\n",
            "    return False\n",
        )],
        suites=["test_analysis.py"],
        caught_by=["is a category, not a requirement"],
    ),
    Injection(
        key="bullet-clause",
        defect="a flattened bullet list is one clause",
        was="an ISM control's SSH settings came back as a single span, and a 60-second "
            "login timeout was read as being about log retention because another bullet "
            "in the same span mentioned logging",
        path="wacc/thresholds.py",
        edits=[(
            '_CLAUSE_BREAKS = (". ", "; ", ": ", "\\n", " - ", " \u2022 ", " \u2014 ")\n',
            '_CLAUSE_BREAKS = (". ", "; ", ": ", "\\n")\n',
        )],
        suites=["test_analysis.py"],
        caught_by=["breaks at the bullet"],
    ),
    Injection(
        key="incompatible-blind",
        defect="no pair of bounds is ever incompatible",
        was="the check that two stated figures cannot both be met was written over a "
            "list that happened to be empty, so it passed without deciding anything",
        path="wacc/analysis.py",
        edits=[(
            '        if self.left.canonical is None or self.right.canonical is None:\n            return False\n',
            '        return False\n        if self.left.canonical is None or self.right.canonical is None:\n            return False\n',
        )],
        suites=["test_analysis.py"],
        caught_by=["an incompatible pair is offered for reading, never asserted"],
    ),
    Injection(
        key="absent-reads-as-silent",
        defect="a framework that did not load is drawn as one that said nothing",
        was="a shipped package holds nine of the eighteen registered frameworks, and the "
            "other nine were drawn as empty columns. A multi-factor query in a shipped "
            "build reported that the SOCI Act requires nothing, which is a wrong answer "
            "rather than a missing one",
        path="wacc/analysis.py",
        edits=[(
            "                    absent=corpus.absent_frameworks.get(framework.key, \"\"),\n",
            "                    absent=\"\",\n",
        )],
        suites=["test_render.py"],
        caught_by=["is reported as absent"],
    ),
    Injection(
        key="shipped-set-incomplete",
        defect="a file the package imports is excluded from the shipping set",
        was="the rules said what may ship and nothing said whether what ships runs. A "
            "package missing one module it imports is broken, and the check that would "
            "have caught it did not exist",
        path="wacc/packaging.py",
        edits=[(
            'NOISE_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".swp")\n',
            'NOISE_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".swp", "search.py")\n',
        )],
        suites=["test_packaging.py"],
        caught_by=["the shipping set alone answers a query"],
    ),
    Injection(
        key="attribution-dropped",
        defect="a result carries no acknowledgement",
        was="the OAG licence grants reproduction provided the source is acknowledged. "
            "Without the acknowledgement the grant does not apply and the text is being "
            "redistributed without permission",
        path="wacc/analysis.py",
        edits=[(
            '        out: List[Tuple[str, str]] = []\n        seen = set()\n        for control in self.controls:\n            framework = self.corpus_frameworks.get(control.framework_key)\n',
            '        out: List[Tuple[str, str]] = []\n        return out\n        seen = set()\n        for control in self.controls:\n            framework = self.corpus_frameworks.get(control.framework_key)\n',
        )],
        suites=["test_packaging.py"],
        caught_by=["carries the OAG acknowledgement"],
    ),

    # -- presentation ------------------------------------------------------

    Injection(
        key="falsy-jurisdiction",
        defect="jurisdiction is tested for truth rather than for presence",
        was="Jurisdiction.WA is 0, so `if framework.jurisdiction` was False for exactly "
            "the rows a WA entity reads first, and the export dropped them",
        path="wacc/render/export.py",
        edits=[(
            "        framework.jurisdiction.name if framework.jurisdiction is not None else \"\",\n",
            "        framework.jurisdiction.name if framework.jurisdiction else \"\",\n",
        )],
        suites=["test_render.py"],
        caught_by=["WA frameworks export with their jurisdiction"],
    ),
    Injection(
        key="pipe-unescaped",
        defect="a pipe in control text is not escaped for markdown",
        was="a pipe inside a cell splits it into two columns and the table stops being a "
            "table from that row down",
        path="wacc/render/export.py",
        edits=[(
            '    text = " ".join((text or "").split()).replace("|", "\\\\|")\n',
            '    text = " ".join((text or "").split())\n',
        )],
        suites=["test_render.py"],
        caught_by=["survive as one cell"],
        note="the sweep over the rendered table cannot fail on this corpus: three of "
             "4,917 controls carry a pipe, all three are WA CSP, and none of them "
             "answers the subject the case renders. The case that does fail builds a "
             "control with a pipe in it. Running it found a second defect — the "
             "framework name and the identifier were written into the row without "
             "going through the cell escaper at all.",
    ),
    Injection(
        key="vw-columns",
        defect="a framework column is sized in vw",
        was="a vw column keeps the column count fixed and reflows the text instead, so a "
            "wider screen buys wider paragraphs rather than more frameworks",
        path="wacc/render/html.py",
        edits=[(
            "td.col, th.col {\n"
            "  width: var(--comfortable); min-width: var(--comfortable); max-width: var(--comfortable);\n"
            "}\n",
            "td.col, th.col {\n"
            "  width: 23vw; min-width: 23vw; max-width: 23vw;\n"
            "}\n",
        )],
        suites=["test_render.py"],
        caught_by=["no column is sized in vw"],
    ),
    Injection(
        key="unescaped-html",
        defect="control text and the query go into the page unescaped",
        was="control text is publisher text and the query is typed by a person; neither "
            "is markup, and an angle bracket in either one rewrites the page",
        path="wacc/render/html.py",
        edits=[(
            "def esc(value: Optional[str]) -> str:\n"
            '    return _html.escape(value or "", quote=True)\n',
            "def esc(value: Optional[str]) -> str:\n"
            '    return value or ""\n',
        )],
        suites=["test_render.py"],
        caught_by=["escaped into the page"],
    ),
    Injection(
        key="density-forgotten",
        defect="the density choice is not remembered",
        was="a reader who prefers compact had to re-choose it on every search",
        path="wacc/render/html.py",
        edits=[
            ("    try { return localStorage.getItem(key) || fallback; } "
             "catch (e) { return fallback; }\n",
             "    return fallback;\n"),
            ("    try { localStorage.setItem(key, value); } catch (e) {}\n", "\n"),
        ],
        suites=["test_render.py"],
        caught_by=["the density choice is remembered"],
        note="retargeted when the script grew a second remembered setting. The two "
             "try/catch blocks became read() and write() helpers shared by density and "
             "the framework show/hide bar, so the lines this entry named no longer "
             "existed and the entry reported stale rather than passing quietly.",
    ),
    Injection(
        key="binds-anywhere",
        defect="the server binds to any host it is given",
        was="the corpus holds import-only publisher text, and a tool that serves it to "
            "the LAN is redistributing it",
        path="wacc/serve.py",
        edits=[(
            '    if args.host not in ("127.0.0.1", "localhost", "::1"):\n',
            "    if False:\n",
        )],
        suites=["test_render.py"],
        caught_by=["binding to anything but localhost is refused"],
    ),

    # -- packaging ---------------------------------------------------------

    Injection(
        key="licence-forgotten",
        defect="no corpus file is treated as import-only",
        was="half this corpus is publisher text that may not be redistributed, and a "
            "build that includes one of those is a licence breach that will not announce "
            "itself",
        path="wacc/packaging.py",
        edits=[
            ("        if framework.licence is Licence.SHIPPABLE:\n            continue\n",
             "        if True:\n            continue\n"),
            ("    for source in DETAIL_SOURCES:\n", "    for source in ():\n"),
        ],
        suites=["test_packaging.py"],
        caught_by=["is absent from the shipping set", "are named and absent"],
        note="every case in the 'nothing forbidden ships' group asked packaging which "
             "files are forbidden and then asked whether any of them shipped. With the "
             "licence rule broken the answer is an empty list and all of them pass, "
             "which is the licence breach passing its own audit. The cases that fail "
             "read the list off the registry and off four names written down in the "
             "test.",
    ),
    # -- what the extracts quote -------------------------------------------
    #
    # These four inject into the corpus JSON rather than into tools/, because the JSON is
    # what the suite reads and what a build ships. Re-running the extractor takes minutes
    # of pdfplumber and writes into data/corpus, and the defect being checked for is the
    # one that reached the corpus.

    Injection(
        key="caption-misattributed",
        defect="a row is stored under the caption of a different table",
        was="SP 800-57's Table 2 caption shared a baseline with a full stop from the "
            "paragraph above, so the anchored match missed it and the page-break "
            "fallback carried Table 1's caption onto it. Five rows of comparable key "
            "strengths were in the corpus as suggested cryptoperiods",
        path="data/corpus/nist-800-57pt1.json",
        edits=[(
            '"caption": "Table 2: Comparable security strengths of symmetric block cipher and asymmetric-key algorithms",\n     "text": "Table 2: Comparable security strengths of symmetric block cipher and asymmetric-key algorithms \u2014 256; Symmetric Key Algorithms: AES-256; FFC (DSA, DH, MQV): L = 15360 N = 512; IFC* (RSA): k = 15360; f = 512+"',
            '"caption": "Table 1: Suggested cryptoperiods for key types",\n     "text": "Table 1: Suggested cryptoperiods for key types \u2014 256; Symmetric Key Algorithms: AES-256; FFC (DSA, DH, MQV): L = 15360 N = 512; IFC* (RSA): k = 15360; f = 512+"',
        )],
        suites=["test_extracts.py"],
        caught_by=["no cryptoperiod row states a key size"],
    ),
    Injection(
        key="prose-as-table-row",
        defect="a paragraph reported as a one-column table is stored as a row",
        was="pdfplumber read five narrative paragraphs on SP 800-57 page 65 as a "
            "six-row table, and they entered the corpus as suggested cryptoperiods",
        path="data/corpus/nist-800-57pt1.json",
        edits=[(
            '"text": "Table 1: Suggested cryptoperiods for key types \u2014 1. Private Signature Key; 1 to 3 years; \u2212"',
            '"text": "Table 1: Suggested cryptoperiods for key types \u2014 publication of this Recommendation using currently '
            'known methods. Advances in factoring algorithms may affect these"',
        )],
        suites=["test_extracts.py"],
        caught_by=["no stored row is running prose"],
    ),
    Injection(
        key="welded-footnote",
        defect="a footnote marker is welded to the unit of a stated figure",
        was="'< 2 years61' is footnote 61 on a two-year cryptoperiod. The threshold "
            "reader saw no quantity in it at all, so three of the document's stated "
            "cryptoperiods were invisible to every comparison",
        path="data/corpus/nist-800-57pt1.json",
        edits=[(
            "10. Private Key Transport Key; < 2 years",
            "10. Private Key Transport Key; < 2 years61",
        )],
        suites=["test_extracts.py"],
        caught_by=["no figure has a footnote marker welded to its unit"],
    ),
    Injection(
        key="wrapped-word",
        defect="a word the page broke across a line is joined with a space",
        was="ten controls across six extractors read 'enterprise- wide', 'need- to-know', "
            "'internet- facing' and 'user- addressable'. A PDF has no line-break "
            "character, so an extractor joining a wrapped line with a space breaks the "
            "word, and what reaches the corpus is not what the publisher wrote",
        path="data/corpus/c2m2.json",
        edits=[(
            "coordinated with the organization\u2019s enterprise-wide risk management",
            "coordinated with the organization\u2019s enterprise- wide risk management",
        )],
        suites=["test_extracts.py"],
        caught_by=["no control carries a word the page broke"],
    ),
    Injection(
        key="suspended-hyphen-closed",
        defect="a real suspended hyphen is closed up as though it were a break",
        was="NIST writes 'security- and privacy-related documentation'. Mending that the "
            "way a wrapped word is mended produces 'security-and', so the rule has to "
            "tell a suspended hyphen from a broken word",
        path="tools/textjoin.py",
        edits=[('_SUSPENDED = ("and", "or")\n', "_SUSPENDED = ()\n")],
        suites=["test_extracts.py"],
        caught_by=["leaves a suspended hyphen"],
    ),
    Injection(
        key="corpus-clobbered",
        defect="a curated corpus file is overwritten by another tool",
        was="tools/extract_nist_pdf.py also had SP 800-88 in its document list and wrote "
            "the same path, replacing 15 checked statements with one unchecked sentence "
            "on whichever run went last",
        path="data/corpus/nist-800-88.json",
        edits=[(
            '"note": "This publication abbreviates',
            '"unused": "This publication abbreviates',
        )],
        suites=["test_extracts.py"],
        caught_by=["carrying its own warning"],
    ),
    Injection(
        key="source-file-renamed",
        defect="a framework names a source file that is not on disk",
        was="800-131A was recorded as nist-sp-800-131ar2.pdf for a file called "
            "NIST.SP.800-131Ar2.pdf. The corpus loads from the extracted JSON, so "
            "nothing broke and nothing said anything; only a refresh would have found it",
        path="wacc/registry.py",
        edits=[(
            '        source_file="documents/NIST.SP.800-131Ar2.pdf",\n',
            '        source_file="nist-sp-800-131ar2.pdf",\n',
        )],
        suites=["test_packaging.py"],
        caught_by=["source file is on disk under the name recorded"],
    ),
    Injection(
        key="gitignore-drifted",
        defect="the .gitignore no longer matches the shipping rules",
        was="what may be committed and what may ship are one question. Answered in two "
            "places they drift, and the drift is invisible until an import-only extract "
            "is already in a commit",
        path=".gitignore",
        edits=[("wa-csp.json\n", "")],
        suites=["test_packaging.py"],
        caught_by=["still matches the shipping rules", "cannot be committed"],
    ),
    Injection(
        key="packaging-vacuous",
        defect="the packaging rules report catching nothing",
        was="a packaging check that passes because there is nothing left to catch has "
            "stopped checking, and this is the check that says so",
        path="wacc/packaging.py",
        edits=[(
            "            if in_excluded_dir:\n"
            '                caught.append((path, "excluded directory"))\n'
            "            elif name.lower().endswith(SOURCE_SUFFIXES):\n"
            '                caught.append((path, "publisher source document"))\n'
            "            elif name in forbidden_names:\n"
            '                caught.append((path, "import-only publisher text"))\n',
            "            continue\n",
        )],
        suites=["test_packaging.py"],
        caught_by=["the rules excluded"],
    ),
    # -- the second renderer and the panel ---------------------------------
    #
    # Every case here guards something added when the card view was built. A defence with
    # no injection beside it is a defence nobody has ever seen fail.
    Injection(
        key="highlight-escape-order",
        defect="control text is marked before it is escaped",
        was="marking first inserts markup into publisher text and then escapes the marks "
            "along with it, so the reader sees the tag names and a control containing a "
            "less-than sign has had markup put inside it",
        path="wacc/render/highlight.py",
        edits=[(
            '        out.append(_html.escape(text[cursor:found.start()], quote=True))\n',
            '        out.append(text[cursor:found.start()])\n',
        )],
        suites=["test_render.py"],
        caught_by=["escaped before, between and after the marks",
                   "escaped even between two marks"],
    ),
    Injection(
        key="highlight-marks-short-stems",
        defect="every expanded stem is marked, however short",
        was="'is', 'an', 'of' and 'or' are all in the expanded stem set. Marking them "
            "marks half of every control on the page, and a page where everything is "
            "marked says nothing about why any control is on it",
        path="wacc/render/highlight.py",
        edits=[("MIN_MARKED_STEM = 3\n", "MIN_MARKED_STEM = 0\n")],
        suites=["test_render.py"],
        caught_by=["shorter than"],
    ),
    Injection(
        key="highlight-one-strength",
        defect="a concept's words are marked as strongly as the reader's own",
        was="'patch applications' expands to twenty-five stems including 'system', "
            "'security' and 'management'. Marked at full strength they drown the two "
            "words the reader actually typed",
        path="wacc/render/highlight.py",
        edits=[('            css = "mark wide"\n', '            css = "mark"\n')],
        suites=["test_render.py"],
        caught_by=["marked differently from one a concept added"],
    ),
    Injection(
        key="card-view-drops-silent",
        defect="the card view leaves out frameworks with nothing to say",
        was="an empty column looks like clutter until you remember the tool exists to "
            "say what requires what. A framework left off the screen reads as not asked "
            "rather than asked and silent, which is the defect the grid was built to "
            "avoid and the card view reintroduced",
        path="wacc/render/html.py",
        edits=[(
            "        columns.append(\n"
            '            \'<div class="cardcol" data-fw="%s">%s%s</div>\'\n'
            "            % (esc(framework.key), head, body)\n"
            "        )\n",
            "        if controls:\n"
            "            columns.append(\n"
            '                \'<div class="cardcol" data-fw="%s">%s%s</div>\'\n'
            "                % (esc(framework.key), head, body)\n"
            "            )\n",
        )],
        suites=["test_render.py"],
        caught_by=["every framework is a column in the card view",
                   "the card view draws three kinds of empty"],
    ),
    Injection(
        key="card-text-unescaped",
        defect="the card view writes control text into the page unescaped",
        was="the grid's escaping case covers the grid. A second renderer is a second "
            "surface, and the identifier on a card sits inside an anchor where an "
            "unescaped tag runs rather than showing",
        path="wacc/render/html.py",
        edits=[(
            '    parts.append(\'<div class="body">%s</div>\' % mark(body, typed, widened))\n',
            '    parts.append(\'<div class="body">%s</div>\' % body)\n',
        )],
        suites=["test_render.py"],
        caught_by=["escaped into the card view"],
    ),
    Injection(
        key="grid-cell-loses-framework-key",
        defect="grid cells no longer carry the key the show/hide bar toggles",
        was="hiding a framework hid its column header and left its cells in place, so "
            "every column to the right of it sat under the wrong heading — a crosswalk "
            "reporting the wrong publisher against a control",
        path="wacc/render/html.py",
        edits=[(
            '            cells.append(cell.replace("<td ", \'<td data-fw="%s" \' % esc(framework.key), 1))\n',
            "            cells.append(cell)\n",
        )],
        suites=["test_render.py"],
        caught_by=["carries the key the show/hide bar toggles"],
    ),
    Injection(
        key="panel-unescaped",
        defect="the control panel writes publisher text into the document unescaped",
        was="the panel is put into an open page with innerHTML. Unescaped text there is "
            "the same defect as unescaped text in the page, and the page's own case does "
            "not reach it",
        path="wacc/render/html.py",
        edits=[(
            '        parts.append("<h5>%s</h5><p>%s</p>" % (esc(label), esc(statement.text)))\n',
            '        parts.append("<h5>%s</h5><p>%s</p>" % (esc(label), statement.text))\n',
        )],
        suites=["test_render.py"],
        caught_by=["escaped into the panel"],
    ),
    Injection(
        key="published-procedure-unattributed",
        defect="a published assessment procedure is rendered without its publisher",
        was="NIST writes the 800-53A objectives and this tool does not. Printing one "
            "unattributed beside a derived procedure puts NIST's name behind a sentence "
            "NIST never wrote",
        path="wacc/render/html.py",
        edits=[(
            '        parts.append("<h5>Published procedure \u2014 %s</h5><p>%s</p>" % (\n'
            '            esc(statement.published_by or "the publisher"), esc(statement.text),\n'
            "        ))\n",
            '        parts.append("<h5>Procedure</h5><p>%s</p>" % esc(statement.text))\n',
        )],
        suites=["test_render.py"],
        caught_by=["names the publisher who wrote it"],
    ),
    Injection(
        key="risk-summary-merges-silent-and-absent",
        defect="the risk summary reports absent frameworks as silent ones",
        was="'not addressed by' covered both a publisher that was asked and requires "
            "nothing, and a publisher nobody asked. An executive reading the first as "
            "the second concludes an obligation does not exist",
        path="wacc/render/export.py",
        edits=[(
            '            "Loaded and silent on it: %s. Those publishers were asked and require "\n'
            '            "nothing here."\n',
            '            "Not addressed by: %s."\n',
        )],
        suites=["test_render.py"],
        caught_by=["separates silent frameworks from absent ones"],
    ),
    Injection(
        key="test-plan-without-signoff",
        defect="the test plan has nowhere to record a result",
        was="a test whose result nobody recorded was not carried out. A plan with no "
            "place to write it invites the result to live in an email",
        path="wacc/render/export.py",
        edits=[(
            '        out.append("| Tested by | Date | Result | Workpaper reference |")\n'
            '        out.append("| --- | --- | --- | --- |")\n'
            '        out.append("|  |  |  |  |")\n',
            '        out.append("")\n',
        )],
        suites=["test_render.py"],
        caught_by=["somewhere to record the result"],
    ),
    Injection(
        key="card-columns-unmeasured",
        defect="the card view is sized by a number that was never measured",
        was="a stylesheet with its own widths is a second source of truth. The grid's "
            "figures do not describe a view with no pinned column and a wider column, "
            "so reusing them reports a framework count the reader never sees",
        path="wacc/render/layout.py",
        edits=[("CARD_COMFORTABLE = 360\n", "CARD_COMFORTABLE = 300\n")],
        suites=["test_render.py"],
        caught_by=["fits 3 card columns", "fits 5 card columns"],
        note="the constants case does not fail here and should not. The page reads its "
             "widths from the layout module, so changing the constant changes both "
             "together and they still agree — which is exactly what that case asserts. "
             "The arithmetic cases are the defence: they hold the measured column count "
             "against the recorded one.",
    ),
]


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------


def _stage() -> str:
    """A copy of the tree to break.

    data/raw is 136 MB of publisher PDFs that no test reads and the packaging rules only
    need the names of, so it is hard-linked rather than copied. Nothing here writes to
    anything outside wacc/, so the shared inodes are safe, and the alternative — standing
    in empty files of the same names — would make the packaging check pass against a tree
    that is not the real one.
    """
    staging = tempfile.mkdtemp(prefix="wacc-injected-")
    target = os.path.join(staging, "tree")

    def ignore(directory, names):
        skip = {n for n in names if n in ("__pycache__", ".git")}
        if os.path.normpath(directory) == os.path.normpath(os.path.join(ROOT, "data")):
            skip.add("raw")
        return skip

    shutil.copytree(ROOT, target, ignore=ignore)
    raw = os.path.join(ROOT, "data", "raw")
    if os.path.isdir(raw):
        subprocess.run(["cp", "-al", raw, os.path.join(target, "data", "raw")], check=True)
    return target


def _fail_lines(output: str) -> List[str]:
    return [
        line.strip() for line in output.splitlines() if line.startswith("  FAIL")
    ]


# A suite that never returns has not caught anything. Injections have twice turned a
# case into a block rather than a failure — a removed host guard ran serve_forever, and
# an unbounded walk did not finish — and both are reported as hangs rather than being
# waited out, because a test that hangs under a defect reports nothing in CI either.
SUITE_TIMEOUT = 150


def _run_suite(tree: str, suite: str) -> Tuple[int, str, float]:
    started = time.time()
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, os.path.join(tree, "tests", suite)],
            capture_output=True, text=True, cwd=tree, env=environment,
            timeout=SUITE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return HUNG, "", time.time() - started
    return result.returncode, result.stdout + result.stderr, time.time() - started


@dataclass
class Outcome:
    injection: Injection
    applied: bool
    stale: str = ""
    caught: bool = False
    missing: List[str] = field(default_factory=list)
    fired: List[str] = field(default_factory=list)
    new_failures: int = 0
    suites_failed: List[str] = field(default_factory=list)
    hung: List[str] = field(default_factory=list)
    crashed: List[str] = field(default_factory=list)
    tail: str = ""
    seconds: float = 0.0


def _apply(tree: str, injection: Injection) -> str:
    """Write the defect in. Returns an empty string, or why the entry is stale."""
    path = os.path.join(tree, injection.path)
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    changed = source
    for old, new in injection.edits:
        count = changed.count(old)
        if count != 1:
            return "%s matches %d times in %s" % (
                repr(old[:60] + ("..." if len(old) > 60 else "")), count, injection.path
            )
        changed = changed.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(changed)
    return ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = None
    if "--only" in argv:
        only = argv[argv.index("--only") + 1]
    verbose = "-v" in argv or "--verbose" in argv

    matrix = [i for i in MATRIX if only is None or i.key == only]
    if not matrix:
        print("no injection named %r. Known keys: %s"
              % (only, ", ".join(i.key for i in MATRIX)))
        return 2

    print("wacc injected-regression matrix — %d defect%s put back one at a time\n"
          % (len(matrix), "" if len(matrix) == 1 else "s"))

    tree = _stage()
    originals: Dict[str, str] = {}
    for injection in matrix:
        path = os.path.join(tree, injection.path)
        if path not in originals:
            with open(path, encoding="utf-8") as handle:
                originals[path] = handle.read()

    baselines: Dict[str, Tuple[int, Set[str]]] = {}
    outcomes: List[Outcome] = []
    try:
        wanted = []
        for injection in matrix:
            for suite in injection.suites:
                if suite not in wanted:
                    wanted.append(suite)
        print("baseline (the suite untouched, so an injection cannot inherit a failure)")
        dirty = []
        for suite in wanted:
            code, output, elapsed = _run_suite(tree, suite)
            baselines[suite] = (code, set(_fail_lines(output)))
            print("   %-26s %-7s %4.1fs   %d FAIL line%s already present"
                  % (suite, "ok" if code == 0 else "FAILED", elapsed,
                     len(baselines[suite][1]),
                     "" if len(baselines[suite][1]) == 1 else "s"))
            if code != 0:
                dirty.append(suite)
        if dirty:
            print("\nbaseline is not clean: %s" % ", ".join(dirty))
            print("Fix the tree first. Injecting into a failing suite proves nothing.")
            return 2
        print()

        print("injections")
        for injection in matrix:
            started = time.time()
            stale = _apply(tree, injection)
            if stale:
                outcomes.append(Outcome(injection, applied=False, stale=stale))
                print("   %-22s MATRIX STALE  %s" % (injection.key, stale))
                continue

            fired: List[str] = []
            failed_suites: List[str] = []
            hung: List[str] = []
            crashed: List[str] = []
            tail = ""
            new_total = 0
            for suite in injection.suites:
                code, output, _ = _run_suite(tree, suite)
                if code == HUNG:
                    hung.append(suite)
                baseline_code, baseline_fails = baselines[suite]
                fresh = [l for l in _fail_lines(output) if l not in baseline_fails]
                new_total += len(fresh)
                if code != baseline_code:
                    failed_suites.append(suite)
                # Non-zero with nothing reported is a crash, not a pass and not a
                # caught defect. The suite stopped before its cases could speak, so
                # the tail of its output is kept: that is the only evidence there is.
                if code not in (baseline_code, HUNG) and not fresh:
                    crashed.append(suite)
                    tail = "\n".join(output.strip().splitlines()[-4:])
                for wanted_text in injection.caught_by:
                    if any(wanted_text in line for line in fresh):
                        fired.append("%s: %s" % (suite, wanted_text))
                if verbose:
                    for line in fresh[:6]:
                        print("        %s" % line)

            for path, source in originals.items():
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(source)

            missing = [
                w for w in injection.caught_by
                if not any(w in f for f in fired)
            ]
            caught = bool(injection.caught_by) and not missing
            if not injection.caught_by:
                # An entry with no named case is not yet finished. It is reported by
                # what fired so the case can be named, and it never counts as caught.
                caught = False
            if hung or crashed:
                caught = False
            outcome = Outcome(
                injection=injection, applied=True, caught=caught, missing=missing,
                fired=fired, new_failures=new_total, suites_failed=failed_suites,
                seconds=time.time() - started, hung=hung, crashed=crashed, tail=tail,
            )
            outcomes.append(outcome)
            if hung:
                mark = "HUNG"
            elif crashed:
                mark = "CRASHED"
            elif caught:
                mark = "caught"
            elif new_total:
                mark = "NOT NAMED" if not injection.caught_by else "WRONG CASE"
            else:
                mark = "NOT CAUGHT"
            print(
                "   %-22s %-11s %-26s %3d new FAIL%s  %4.1fs"
                % (injection.key, mark, ", ".join(injection.suites),
                   new_total, " " if new_total == 1 else "s", outcome.seconds)
            )
    finally:
        for path, source in originals.items():
            if os.path.exists(path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(source)
        shutil.rmtree(os.path.dirname(tree), ignore_errors=True)

    # -- the matrix --------------------------------------------------------

    print("\n" + "-" * 78)
    print("%-22s %-10s %s" % ("defect", "status", "the case that fires"))
    print("-" * 78)
    for outcome in outcomes:
        if not outcome.applied:
            print("%-22s %-10s %s" % (outcome.injection.key, "stale", outcome.stale))
            continue
        if outcome.hung:
            status = "HUNG"
        elif outcome.crashed:
            status = "CRASHED"
        elif outcome.caught:
            status = "caught"
        elif not outcome.injection.caught_by:
            status = "unnamed"
        else:
            status = "GAP"
        first = outcome.fired[0].split(": ", 1)[1] if outcome.fired else "—"
        if outcome.hung:
            first = "%s never returned" % ", ".join(outcome.hung)
        elif outcome.crashed:
            first = "%s stopped before its cases ran" % ", ".join(outcome.crashed)
        print("%-22s %-10s %s" % (outcome.injection.key, status, first[:44]))

    noted = [o for o in outcomes if o.injection.note]
    if noted:
        print("\nWHAT THE INJECTION TAUGHT — where the defence turned out to sit:")
        for outcome in noted:
            print("  %s" % outcome.injection.key)
            for line in _wrap(outcome.injection.note, 74, "      "):
                print(line)

    gaps = [o for o in outcomes if o.applied and not o.caught]
    stale = [o for o in outcomes if not o.applied]
    caught = [o for o in outcomes if o.caught]

    print("-" * 78)
    print("%d of %d defects are caught by a named case" % (len(caught), len(outcomes)))

    if stale:
        print("\nSTALE ENTRIES — the code moved and these no longer describe it:")
        for outcome in stale:
            print("  %-20s %s" % (outcome.injection.key, outcome.stale))

    if gaps:
        print("\nGAPS — the defect was reintroduced and no named case failed:")
        for outcome in gaps:
            print("  %s" % outcome.injection.key)
            print("      defect: %s" % outcome.injection.defect)
            print("      was:    %s" % outcome.injection.was)
            if outcome.hung:
                print("      the suite did not return in %ds: the defect turns a case "
                      "into a block, not a failure" % SUITE_TIMEOUT)
            elif outcome.crashed:
                print("      %s exited non-zero having reported no case: the defect "
                      "stops the suite before the case that names it runs"
                      % ", ".join(outcome.crashed))
                for line in outcome.tail.splitlines():
                    print("        %s" % line)
            elif outcome.new_failures:
                print("      %d unrelated case%s did fail; none of them is the named one"
                      % (outcome.new_failures,
                         "" if outcome.new_failures == 1 else "s"))
                for entry in outcome.fired:
                    print("      fired:  %s" % entry)
            else:
                print("      the suite passed with the defect in place")
            for text in outcome.missing:
                print("      wanted: a FAIL line containing %r" % text)

    return 1 if (gaps or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
