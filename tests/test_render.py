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
import urllib.request
from http.server import ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.analysis import analyse, gather  # noqa: E402
from wacc.build import build  # noqa: E402
from wacc.render import export, html, layout, text  # noqa: E402
from wacc.render.layout import (  # noqa: E402
    COLUMN_GAP,
    COMFORTABLE,
    COMPACT,
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
        markdown.count("## Tier") == 5,
        "export", "markdown draws all five bands",
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
    check.expect(
        "<script>" in page and "http" not in page.split("<script>")[1].split("</script>")[0],
        "html", "the page fetches nothing",
        "everything stays on the machine",
    )
    hostile = _replace(
        payload.controls[0],
        identifier="<img src=x onerror=alert(1)>",
        text="a & b <script>alert(1)</script>",
    )
    hostile_payload = analyse(corpus, "x & y <b>", [hostile], display=[hostile])
    hostile_page = html.render(corpus, hostile_payload)
    check.expect(
        "<script>alert(1)</script>" not in hostile_page
        and "&amp;" in hostile_page
        and "&lt;script&gt;" in hostile_page,
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
        absent_payload.frameworks_present == len(corpus.frameworks) - 1,
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
            "/?q=AC-6(5)",
            "/?q=",
            "/export.csv?q=backups",
            "/export.md?q=backups",
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
            and "text/markdown" in results["/export.md?q=backups"][1],
            "server", "exports are served with their own content types",
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
