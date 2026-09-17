"""The three renderers, the layout arithmetic and the local server.

Every case names the defect it came from. The layout cases are arithmetic rather than
taste: how many frameworks a reader sees at once is the only layout question that matters,
and it is answerable without a browser.
"""

import os
import re
import sys
import threading
import time
from dataclasses import replace as _replace
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.analysis import analyse, gather  # noqa: E402
from wacc.build import build  # noqa: E402
from wacc.render import export, html, layout, text  # noqa: E402
from wacc.render.layout import (  # noqa: E402
    CARD_COMFORTABLE,
    CARD_COMPACT,
    COLUMN_GAP,
    COMFORTABLE,
    COMPACT,
    EXPECTED_CARD_COLUMNS,
    EXPECTED_COLUMNS,
    MEASURED_WIDTHS,
    PINNED,
    columns_at,
)
from wacc.search import SearchIndex  # noqa: E402
from wacc.serve import State, _handler  # noqa: E402

SUBJECT = "how quickly must a cyber security incident be reported"


def _replace_corpus(corpus, absent):
    """The same corpus, with some frameworks marked as not loaded."""
    from dataclasses import replace as _dc_replace

    return _dc_replace(corpus, absent_frameworks=dict(absent))


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def expect(self, condition, area, detail, why=""):
        if condition:
            print("  pass  %-11s %s" % (area, detail))
        else:
            self.failed += 1
            print("  FAIL  %-11s %s" % (area, detail))
            if why:
                print("        from: %s" % why)


def run() -> int:
    corpus, _ = build(verbose=False)
    index = SearchIndex(corpus)
    check = Check()

    deep = gather(corpus, index, SUBJECT)
    shown = [hit.control for hit in index.search(SUBJECT, limit=25).hits]
    payload = analyse(corpus, SUBJECT, deep, display=shown)

    # -- layout ------------------------------------------------------------

    for (width, density), expected in sorted(EXPECTED_COLUMNS.items()):
        fit = columns_at(width, density)
        check.expect(
            fit.columns == expected,
            "layout", "%d px %s fits %d framework columns" % (width, density, expected),
            "the recorded measurement is what a layout change is checked against",
        )
    for (width, density), expected in sorted(EXPECTED_COLUMNS.items()):
        fit = columns_at(width, density)
        check.expect(
            fit.leftover < COMPACT,
            "layout", "%d px %s wastes less than one compact column (%d px)"
            % (width, density, fit.leftover),
            "218 px left over at 1366 compact was most of an unused column, which is "
            "what prompted narrowing the pinned column and the gap",
        )
    check.expect(
        all(
            columns_at(w, "compact").columns >= columns_at(w, "comfortable").columns
            for w in MEASURED_WIDTHS
        ),
        "layout", "compact never shows fewer columns than comfortable",
    )
    check.expect(
        all(
            columns_at(2560, d).columns > columns_at(1366, d).columns
            for d in ("comfortable", "compact")
        ),
        "layout", "a wider screen buys more frameworks, not wider text",
        "a column sized in vw keeps the column count fixed and reflows the text instead",
    )

    # -- the display set is not the analysis set ---------------------------

    check.expect(
        payload.depth > len(payload.controls),
        "payload", "%d controls read, %d shown" % (payload.depth, len(payload.controls)),
        "rendering the analysis set put thirty SOCI provisions on screen, definitions "
        "among them, when the numbers are what needed the depth",
    )
    soci = [
        c for b in payload.bands for c in b.coverage if c.framework.key == "soci-act"
    ]
    check.expect(
        bool(soci) and soci[0].total > len(soci[0].controls) and soci[0].hidden > 0,
        "payload", "a framework reports how many it read as well as how many it shows",
    )

    # -- terminal ----------------------------------------------------------

    rendered = text.render(corpus, payload)
    check.expect(
        rendered.count("TIER ") == 5,
        "text", "all five tier bands are drawn, including empty ones",
        "a band that is not drawn reads as a question nobody asked",
    )
    check.expect(
        "nothing found at this tier" in rendered or all(
            not b.is_empty for b in payload.bands
        ),
        "text", "an empty band says so rather than being silent",
    )
    check.expect(
        "SAYS NOTHING ON THIS SUBJECT" in rendered,
        "text", "frameworks with nothing to say are named",
        "a framework missing from the output reads as not asked rather than silent",
    )
    check.expect(
        all(len(line) <= 80 for line in rendered.split("\n")),
        "text", "no line exceeds the terminal width",
    )
    check.expect(
        "s 30BC(1)" in rendered,
        "text", "the twelve-hour notification provision is on screen",
    )

    # -- export ------------------------------------------------------------

    csv_body = export.to_csv(corpus, payload)
    check.expect(
        "obligation_provenance" in csv_body and "fidelity" in csv_body,
        "export", "every CSV row carries provenance and fidelity",
        "an exported row that lost its source is a claim with no source, and it is the "
        "row that ends up quoted",
    )
    wa_rows = [r for r in csv_body.split("\n") if ",WA CSP," in r]
    check.expect(
        bool(wa_rows) and all(",WA," in r for r in wa_rows),
        "export", "WA frameworks export with their jurisdiction",
        "Jurisdiction.WA is 0, so `if framework.jurisdiction` was False for exactly the "
        "rows a WA entity reads first",
    )
    check.expect(
        csv_body.count("\n") > 20, "export", "the CSV holds the shown controls"
    )

    markdown = export.to_markdown(corpus, payload)
    check.expect(
        "## Outcomes / maturity" in markdown and "## Tier" not in markdown,
        "export", "markdown combines governance and maturity results",
    )
    body_rows = [l for l in markdown.split("\n") if l.startswith("| ") and "---" not in l]
    # Escaped pipes are still pipe characters, so count only the ones that separate cells.
    unescaped = [len(re.findall(r"(?<!\\)\|", l)) for l in body_rows]
    check.expect(
        bool(unescaped) and all(n == 5 for n in unescaped),
        "export", "no markdown cell is broken by a pipe or a newline in control text",
        "a pipe inside a cell splits it into two columns and the table stops being a table",
    )
    # Built rather than looked for. Three controls in the whole corpus carry a pipe and
    # none of them answers this subject, so the case above passed on text that had no
    # pipe in it to escape.
    piped = _replace(
        payload.controls[0],
        identifier="X|1",
        text="disable SMBv1 | SMBv2 and record the decision\nin the register",
    )
    piped_markdown = export.to_markdown(
        corpus, analyse(corpus, "pipes", [piped], display=[piped])
    )
    piped_rows = [
        l for l in piped_markdown.split("\n") if l.startswith("| ") and "---" not in l
    ]
    check.expect(
        bool(piped_rows)
        and all(len(re.findall(r"(?<!\\)\|", l)) == 5 for l in piped_rows),
        "export", "a pipe and a newline inside control text survive as one cell",
        "the corpus happens to hold almost no pipes, so the sweep above cannot fail "
        "even when nothing is escaped",
    )

    # -- html --------------------------------------------------------------

    page = html.render(corpus, payload)
    check.expect(
        not re.search(r"\d+(?:\.\d+)?vw", page),
        "html", "no column is sized in vw",
        "a vw column keeps the count fixed and reflows the text, so more screen buys "
        "nothing",
    )
    check.expect(
        ("--comfortable: %dpx" % COMFORTABLE) in page
        and ("--compact: %dpx" % COMPACT) in page
        and ("--pinned: %dpx" % PINNED) in page,
        "html", "the page's widths come from the measured layout constants",
        "a CSS file with its own numbers is a second source of truth that drifts",
    )
    check.expect(
        "position: sticky" in page and "th.pin, td.pin" in page,
        "html", "the left column pins",
    )
    check.expect(
        "text-overflow: ellipsis" in page and "white-space: nowrap" in page,
        "html", "column headers clamp to one line",
        "a header that wraps changes the height of every row in the grid",
    )
    check.expect(
        page.count("<th class=\"col\" title=") == len(corpus.frameworks),
        "html", "every framework is a column, with its full name on hover",
    )
    check.expect(
        "localStorage" in page and "wacc-density" in page,
        "html", "the density choice is remembered",
    )
    check.expect(
        "-webkit-line-clamp: 2" in page,
        "html", "compact clamps the body to two lines",
    )
    check.expect(
        "says nothing on this subject" in page,
        "html", "an empty cell says which kind of nothing it is",
    )
    script_body = page.split("<script>")[1].split("</script>")[0]
    fetch_targets = re.findall(r"fetch\(\s*([^)]+?)\)", script_body)
    check.expect(
        "<script>" in page and "http" not in script_body,
        "html", "the page names no other host",
        "everything stays on the machine",
    )
    # The page does fetch now — the panel under a control, and the two working papers.
    # 'no http in the script' would still pass if a target were built from a variable, so
    # the case is on every target starting at this server's root.
    check.expect(
        bool(fetch_targets)
        and all(t.strip().startswith(("'/", '"/', "button.dataset.copy"))
                for t in fetch_targets),
        "html", "every fetch the page makes is a path on this server",
        "a tool that holds import-only publisher text must not be able to send any of "
        "it somewhere else, and 'no literal http' does not say that on its own",
    )
    check.expect(
        'data-copy="/exec.md' in page and 'data-copy="/plan.md' in page,
        "html", "the copy buttons point at this server's own routes",
    )
    hostile = _replace(
        payload.controls[0],
        identifier="<img src=x onerror=alert(1)>",
        text="a & b <script>alert(1)</script>",
    )
    hostile_payload = analyse(corpus, "x & y <b>", [hostile], display=[hostile])
    hostile_page = html.render(corpus, hostile_payload)
    # The identifier is checked as well as the text, and they are escaped by different
    # code now: the body goes through mark(), which escapes each span itself, and
    # everything else through esc(). Looking only for the script tag in the text meant
    # esc() could be removed entirely with this case still passing.
    check.expect(
        "<script>alert(1)</script>" not in hostile_page
        and "<img src=x" not in hostile_page
        and "&amp;" in hostile_page
        and "&lt;script&gt;" in hostile_page
        and "&lt;img src=x onerror=alert(1)&gt;" in hostile_page,
        "html", "control text and the query are escaped into the page",
        "control text is publisher text and the query is typed, and neither is markup",
    )

    # -- absent is not silent ----------------------------------------------
    #
    # A shipped package holds nine of the eighteen registered frameworks: the rest load
    # from publisher files that cannot be redistributed. Rendering those as an empty
    # column said the SOCI Act requires nothing about multi-factor authentication, in a
    # tool whose whole purpose is to say what requires what. Staged rather than looked
    # for, because the development tree loads everything and the case would never fail.
    absent_corpus = _replace_corpus(corpus, {"soci-act": "soci-act-latest.docx not present"})
    absent_payload = analyse(absent_corpus, SUBJECT, deep, display=shown)
    check.expect(
        [f.key for f, _ in absent_payload.frameworks_absent] == ["soci-act"],
        "absent", "a framework that did not load is reported as absent",
    )
    check.expect(
        "soci-act" not in [f.key for f in absent_payload.frameworks_silent],
        "absent", "an absent framework is not listed as saying nothing",
        "silent and absent are different answers and a reader acts on them differently",
    )
    check.expect(
        absent_payload.frameworks_present == 22,  # 23 families, with SOCI absent; ISM/principles and strategies/E8 share families.
        "absent", "the framework count counts the build, not the registry",
        "'across 12 of 18 frameworks' read as coverage when nine of the eighteen were "
        "not loaded at all",
    )
    absent_text = text.render(absent_corpus, absent_payload)
    check.expect(
        "NOT IN THIS BUILD" in absent_text
        and "soci-act-latest.docx not present" in absent_text,
        "absent", "the terminal names what is missing and why",
    )
    absent_page = html.render(absent_corpus, absent_payload)
    check.expect(
        "not in this build" in absent_page
        and "says nothing on this subject" in absent_page,
        "absent", "the grid draws three kinds of empty, not two",
        "one cell means the publisher requires nothing here and the other means nobody "
        "looked",
    )
    absent_markdown = export.to_markdown(absent_corpus, absent_payload)
    absent_csv = export.to_csv(absent_corpus, absent_payload)
    check.expect(
        "## Not in this build" in absent_markdown
        and "not in this build" in absent_csv,
        "absent", "both exports carry the absence into the working paper",
        "an exported table is what gets pasted into a finding",
    )

    # -- highlighting ------------------------------------------------------
    #
    # Marking the matched words is why scoring is in Python rather than left to FTS5:
    # the reader can see why a control is on screen without a separate explanation. The
    # escaping order is the security property and it only works one way, so the hostile
    # case here is the one that matters.

    from wacc.render.highlight import MIN_MARKED_STEM, mark, marked_count  # noqa: E402
    from wacc.terms import prepare as _prepare  # noqa: E402

    prepared = _prepare("patch applications")
    typed = list(prepared.stems) + list(prepared.alias_stems)
    check.expect(
        marked_count("Patches are patched after patching", typed) == 3,
        "highlight", "a matched word is marked in every form the publisher wrote it",
        "a highlighter that marks only the typed word tells the reader the control "
        "matched on something it did not",
    )
    # Three spans, because there are three and they are escaped by different lines: the
    # text before the first mark, the text between two marks, and the text after the last.
    # A case whose input has no matched word in it exercises only the third, and passes
    # with the other two removed — which is what the matrix caught it doing.
    spans = mark("<script>a</script> patch <b>x</b> patch <i>y</i>", typed)
    check.expect(
        "<script>" not in spans and "<b>" not in spans and "<i>" not in spans
        and spans.count("<mark") == 2
        and "&lt;script&gt;" in spans and "&lt;b&gt;" in spans and "&lt;i&gt;" in spans,
        "highlight", "publisher text is escaped before, between and after the marks",
        "escape after marking and the marks are escaped; mark after escaping and the "
        "offsets no longer line up with the text",
    )
    injected = mark("patch <b>x</b> patch", typed)
    check.expect(
        injected.count("<mark") == 2 and "<b>" not in injected,
        "highlight", "a tag inside control text is escaped even between two marks",
        "marks are inserted at token boundaries and every span between them is escaped "
        "on its own, so a tag cannot survive in the gap",
    )
    short = mark("It is an OS of a system", ["is", "an", "of"])
    check.expect(
        "<mark" not in short,
        "highlight", "a stem shorter than %d characters is not marked" % MIN_MARKED_STEM,
        "'is', 'an' and 'of' are in the expanded stem set and marking them marks half "
        "the page, which says nothing about why any control is there",
    )
    widened = mark("patching the operating system", typed, prepared.concept_stems)
    check.expect(
        'class="mark"' in widened and 'class="mark wide"' in widened,
        "highlight", "a word the reader typed is marked differently from one a concept added",
        "'patch applications' expands to 25 stems including 'system' and 'security'; "
        "marking those at full strength marks most of every control on the page",
    )
    both = mark("patch", ["patch"], ["patch"])
    check.expect(
        'class="mark"' in both and "wide" not in both,
        "highlight", "a stem in both sets is a typed word, not a widened one",
    )

    # -- card view ---------------------------------------------------------

    from wacc.derive import DetailIndex, derive  # noqa: E402
    from wacc.relate import Relations  # noqa: E402

    relations = Relations(corpus)
    details = DetailIndex(corpus, index.weight_of)
    derivations = {
        c.uid: derive(corpus, c, relations, details) for c in payload.controls
    }
    risks = {u: d.risk for u, d in derivations.items() if d.risk}
    crumbs = {}
    for control in payload.controls:
        placement = relations.placement(control.uid)
        if placement is not None:
            crumbs[control.uid] = placement.breadcrumb

    cards = html.render(corpus, payload, view="cards", risks=risks, breadcrumbs=crumbs)
    # Two counts, not one. The first says every framework got a column; the second says
    # no column is missing the key the show/hide bar toggles, which is what a single
    # count of the opening tag would have missed.
    check.expect(
        cards.count('<div class="cardcol"') == len(corpus.frameworks)
        and cards.count('<div class="cardcol" data-fw=') == len(corpus.frameworks),
        "cards", "every framework is a column in the card view, including silent ones",
        "a framework left out of the card view reads as not asked rather than silent, "
        "which is the same defect the grid was built to avoid",
    )
    check.expect(
        cards.count('class="card"') >= len(payload.controls),
        "cards", "every shown control is a card",
    )
    check.expect(
        'class="riskbox"' in cards and "Risk scenario" in cards,
        "cards", "the risk statement is on the card, not behind a click",
        "communicating the risk of an absent control is what the tool is for, so it is "
        "the first thing on a card rather than something to go looking for",
    )
    check.expect(
        cards.count("data-panel=") >= len(payload.controls),
        "cards", "every card offers its test procedure",
    )
    check.expect(
        ("--card: %dpx" % CARD_COMFORTABLE) in cards
        and ("--card-compact: %dpx" % CARD_COMPACT) in cards,
        "cards", "the card widths come from the measured layout constants",
        "a stylesheet with its own numbers is a second source of truth that drifts",
    )
    for (width, density), expected in sorted(EXPECTED_CARD_COLUMNS.items()):
        fit = columns_at(width, density, pinned=False, cards=True)
        check.expect(
            fit.columns == expected,
            "layout", "%d px %s fits %d card columns" % (width, density, expected),
            "the card view has no pinned column and a wider column, so the grid's "
            "figures do not describe it",
        )

    absent_cards = html.render(absent_corpus, absent_payload, view="cards")
    # Measured on the card's own wording. 'says nothing on this subject' appears once per
    # framework in the coverage strip above the columns, so looking for it anywhere on
    # the page passed even when no card column said it at all.
    check.expect(
        "Not in this build." in absent_cards
        and "This framework is loaded and says nothing on this subject."
        in absent_cards,
        "cards", "the card view draws three kinds of empty, as the grid does",
        "one column means the publisher requires nothing here and the other means "
        "nobody looked",
    )
    hostile_cards = html.render(corpus, hostile_payload, view="cards")
    # Measured on the unescaped forms being absent and the escaped forms being present.
    # Looking for 'onerror=alert(1)' anywhere was the wrong measure: an identifier that
    # has been escaped correctly still contains those characters as text, because none of
    # them is one HTML escaping touches, so the case failed on text that was safe.
    check.expect(
        "<script>alert(1)</script>" not in hostile_cards
        and "<img src=x" not in hostile_cards
        and "&lt;script&gt;" in hostile_cards
        and "&lt;img src=x onerror=alert(1)&gt;" in hostile_cards,
        "cards", "control text and identifiers are escaped into the card view",
        "the grid's escaping case does not cover a second renderer, and the identifier "
        "on a card is written inside an anchor, where an unescaped tag would run",
    )
    # The quote is excluded from the character class on purpose. Including it let the
    # pattern match the attribute's own closing quote and then run on into the next
    # attribute, so the case fired on every well-formed anchor on the page. What is left
    # can only match inside the value, because everything before it is a non-quote.
    check.expect(
        not re.search(r'<a href="[^"]*[<>]', hostile_cards)
        and bool(re.search(r'<a href="[^"]*[<>]', '<a href="https://x<b>" rel="noopener"')),
        "cards", "the publisher link on a card is escaped into its attribute",
        "the URL comes from the registry, which is still data, and an unescaped angle "
        "bracket in an href starts writing markup inside the attribute",
    )

    # Every column and every grid cell has to be reachable by the show/hide bar, or a
    # hidden framework hides its header and leaves its cells on screen.
    grid_page = html.render(corpus, payload, view="grid")
    body_cells = re.findall(r"<td (?!class=\"pin\")[^>]*>", grid_page)
    check.expect(
        bool(body_cells) and all("data-fw=" in cell for cell in body_cells),
        "cards", "every framework cell carries the key the show/hide bar toggles",
        "hiding a framework hid its header and left its cells in place, which shifts "
        "every column right of it under the wrong heading",
    )
    check.expect(
        grid_page.count("data-toggle-fw=") == len(corpus.frameworks),
        "cards", "the show/hide bar offers every framework",
    )

    # -- how the query was read --------------------------------------------

    check.expect(
        'class="interp"' in grid_page and 'class="term core"' in grid_page,
        "interp", "the page says how the query was read and which terms it used",
        "a control returned on a word nobody typed looks like a bug until the expansion "
        "is on screen",
    )
    check.expect(
        'class="coverstrip"' in grid_page
        and grid_page.count('<div class="cover ') == len(corpus.frameworks),
        "interp", "the coverage strip covers every framework",
    )

    # -- the landing page --------------------------------------------------

    landing = html.render(corpus, analyse(corpus, "", [], display=[]))
    check.expect(
        landing.count('class="fwcard"') == len(corpus.frameworks),
        "landing", "an empty query answers with what is loaded, not an empty grid",
        "an empty search box is a question about the corpus, and a blank grid answers "
        "it with nothing",
    )
    check.expect(
        "data-search=" in landing,
        "landing", "the landing page offers subjects that can be asked",
    )
    landing_absent = html.render(absent_corpus, analyse(absent_corpus, "", [], display=[]))
    check.expect(
        "not in this build" in landing_absent,
        "landing", "the landing page says which frameworks did not load",
        "judging anything the tool says afterwards depends on knowing what was read",
    )

    # -- the control panel -------------------------------------------------
    #
    # The panel is put into the page with innerHTML, so it is a second escaping surface
    # and the page's own case does not cover it.

    panel_control = payload.controls[0]
    panel = html.control_panel(
        corpus,
        derivations[panel_control.uid],
        placement=relations.placement(panel_control.uid),
        lineage=relations.lineage(panel_control.uid),
    )
    check.expect(
        bool(panel.strip()) and "<h5>" in panel,
        "panel", "a control's panel carries something to read",
    )
    # Derived without relations on purpose. _quote() resolves through
    # relations.quotable_text(uid), and this hostile control shares a uid with a real one,
    # so the corpus text came back and the hostile string never reached the panel — the
    # case passed on text that had nothing in it to escape.
    hostile_derivation = derive(corpus, hostile, None, details)
    hostile_panel = html.control_panel(corpus, hostile_derivation)
    check.expect(
        "<script>alert(1)</script>" not in hostile_panel,
        "panel", "control text is escaped into the panel as well as into the page",
        "the panel is written into the document with innerHTML, so unescaped publisher "
        "text there is the same defect as unescaped text in the page",
    )
    published = [
        u for u, d in derivations.items() if getattr(d, "published", None)
    ]
    if published:
        with_published = html.control_panel(corpus, derivations[published[0]])
        check.expect(
            "Published procedure" in with_published
            and derivations[published[0]].published[0].published_by in with_published,
            "panel", "a published procedure names the publisher who wrote it",
            "NIST writes the 800-53A objectives and this tool does not; an unattributed "
            "one puts NIST's name behind a sentence NIST never wrote",
        )
    else:
        check.expect(
            False,
            "panel", "some control in the payload carries a published procedure",
            "the attribution case above cannot fail if nothing on screen has one",
        )

    # -- the two working papers --------------------------------------------

    summary = export.risk_summary(corpus, absent_payload, risks)
    check.expect(
        export.RISK_CAVEAT in summary,
        "papers", "the risk summary says it states consequence and not likelihood",
        "a reader who takes a consequence statement for a risk rating has been misled "
        "by the omission",
    )
    check.expect(
        "Loaded and silent on it:" in summary and "Not in this build, so not asked:" in summary,
        "papers", "the risk summary separates silent frameworks from absent ones",
        "'not addressed by' covered both, and the two are different answers",
    )
    plan = export.test_plan(corpus, payload, derivations)
    check.expect(
        plan.count("| Tested by | Date | Result | Workpaper reference |")
        == len([u for u in derivations if u in {c.uid for c in payload.controls}]),
        "papers", "every control in the plan has somewhere to record the result",
        "a test nobody recorded the result of was not carried out, and a plan with no "
        "place to write it invites the result to live in an email",
    )
    check.expect(
        export.TEST_CAVEAT in plan and "Derived procedure" in plan,
        "papers", "the plan says its steps are derived rather than a published programme",
    )

    # -- server ------------------------------------------------------------

    state = State(verbose=False)
    server = ThreadingHTTPServer(("127.0.0.1", 8812), _handler(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.3)
    try:
        results = {}
        refused = []
        for path in (
            "/?q=multi-factor+authentication",
            "/?q=multi-factor+authentication&view=grid",
            "/?q=multi-factor+authentication&view=cards",
            "/?q=multi-factor+authentication&view=cards&limit=10",
            "/?q=AC-6(5)",
            "/?q=",
            "/export.csv?q=backups",
            "/export.md?q=backups",
            "/exec.md?q=backups",
            "/plan.md?q=backups",
            "/control?uid=" + urllib.parse.quote(payload.controls[0].uid),
        ):
            # Caught rather than raised. An exception here stops the suite at the first
            # broken route and the cases below — the concurrency one above all — never
            # run, so a real defect reports a traceback and no case name.
            try:
                with urllib.request.urlopen("http://127.0.0.1:8812" + path) as response:
                    results[path] = (response.status, response.headers["Content-Type"],
                                     response.read())
            except Exception as exc:  # noqa: BLE001 - the point of the case
                refused.append("%s (%s)" % (path, type(exc).__name__))
                results[path] = (0, "", b"")
        check.expect(
            not refused and all(status == 200 for status, _, _ in results.values()),
            "server", "every route answers",
            "routes that did not answer: %s" % ", ".join(refused) if refused else "",
        )
        check.expect(
            "text/csv" in results["/export.csv?q=backups"][1]
            and "text/markdown" in results["/export.md?q=backups"][1]
            and "text/markdown" in results["/exec.md?q=backups"][1]
            and "text/markdown" in results["/plan.md?q=backups"][1],
            "server", "exports are served with their own content types",
        )
        panel_route = "/control?uid=" + urllib.parse.quote(payload.controls[0].uid)
        check.expect(
            b"<h5>" in results[panel_route][2]
            and b"<!doctype" not in results[panel_route][2].lower(),
            "server", "the panel route answers with a fragment, not a whole page",
            "the fragment is written into an open document, and a second <html> inside "
            "it is not a document the browser can make sense of",
        )
        # An unknown uid is a thing a stale bookmark does, not an attack. It has to read
        # as an answer rather than as a traceback in the panel.
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8812/control?uid=nosuch:thing"
            ) as response:
                missing = (response.status, response.read())
        except urllib.error.HTTPError as exc:
            missing = (exc.code, exc.read())
        check.expect(
            missing[0] == 404 and b"No control with that identifier" in missing[1],
            "server", "an unknown control answers in words rather than failing",
        )
        wide = results["/?q=multi-factor+authentication&view=cards"][2].decode("utf-8")
        narrow = results["/?q=multi-factor+authentication&view=cards&limit=10"][2].decode(
            "utf-8"
        )
        check.expect(
            wide.count('class="card"') > narrow.count('class="card"'),
            "server", "the per-framework limit changes what is shown",
            "a control on the toolbar that changes nothing is worse than no control",
        )
        check.expect(
            'class="cardcol"' in wide and 'class="cardcol"' not in
            results["/?q=multi-factor+authentication&view=grid"][2].decode("utf-8"),
            "server", "the view in the URL decides the layout, so a link carries it",
            "density is how one person reads and stays local; which view and how many "
            "controls are part of the question and belong in the URL",
        )
        check.expect(
            'class="cardcol"' in results["/?q=multi-factor+authentication"][2].decode("utf-8"),
            "server", "controls open as cards by default",
        )
        # The page prints the publisher's identifier, not the internal uid, so the check
        # is on what a reader sees: one control, and the one that was asked for.
        shown_identifiers = re.findall(
            r'class="ident">([^<]+)<', results["/?q=AC-6(5)"][2].decode("utf-8")
        )
        check.expect(
            shown_identifiers == ["AC-6(5)"],
            "server", "an identifier goes to exact lookup, not to topical search",
            "typing AC-6(5) is a request for one control, and a ranked list of things "
            "mentioning privileged accounts is a different question with a worse answer",
        )
        check.expect(
            len(results["/?q="][2]) > 500,
            "server", "an empty query renders a page rather than failing",
        )

        errors = []

        def hit():
            try:
                urllib.request.urlopen("http://127.0.0.1:8812/?q=patching").read()
            except Exception as exc:  # noqa: BLE001 - the point of the case
                errors.append(exc)

        threads = [threading.Thread(target=hit) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        check.expect(
            not errors,
            "server", "eight concurrent searches all answer",
            "a sqlite3 connection is bound to the thread that made it, and the server "
            "hands requests to whatever thread it likes",
        )
    finally:
        server.shutdown()
        server.server_close()

    from wacc.serve import main as serve_main

    # start= is passed so a removed guard fails here rather than blocking in
    # serve_forever, which is the difference between a case that reports and a suite
    # that hangs.
    started = []
    check.expect(
        serve_main(["--host", "0.0.0.0", "--port", "9"],
                   start=lambda *a, **k: started.append(a)) == 2
        and not started,
        "server", "binding to anything but localhost is refused",
        "the corpus holds import-only publisher text, and a tool that serves it to the "
        "LAN by default is redistributing it",
    )

    print("\nrender: %d failed" % check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(run())
