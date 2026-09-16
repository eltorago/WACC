"""Command-line access to WACC search, controls, exports and the local web app.

    python -m wacc search "media sanitisation"      the crosswalk, in the terminal
    python -m wacc control ISM-1742                 one control in full
    python -m wacc export "backups" --format csv    a working paper
    python -m wacc serve                            the results screen on localhost
    python -m wacc layout                           the column arithmetic
    python -m wacc build                            load the corpus and report

Commands read the local corpus. The web command binds to the local computer by default.
"""

import argparse
import sys
from typing import List, Optional

DISPLAY = 25


def _state(verbose: bool = False):
    from .serve import State

    return State(verbose=verbose)


def _payload(state, query: str):
    return state.payload(query)


def cmd_search(args) -> int:
    from .render import text

    state = _state()
    payload = _payload(state, args.query)
    sys.stdout.write(text.render(state.corpus, payload, width=args.width))
    return 0


def cmd_control(args) -> int:
    from .derive import DetailIndex, derive
    from .lookup import IdentifierIndex, Status
    from .relate import Relations
    from .render import text

    state = _state()
    found = state.lookup.find(args.identifier)
    if found.status is Status.NOT_AN_IDENTIFIER:
        print("%r is not identifier-shaped. Try: python -m wacc search %r"
              % (args.identifier, args.identifier), file=sys.stderr)
        return 2
    if found.status is Status.NONE:
        print(found.note or "no control carries that identifier", file=sys.stderr)
        return 1
    if found.status is Status.WITHDRAWN:
        print(found.note or "withdrawn", file=sys.stderr)
        return 0
    relations = Relations(state.corpus)
    details = DetailIndex(state.corpus, state.index.weight_of)
    if found.status is Status.AMBIGUOUS:
        print(found.note or "several controls carry this identifier", file=sys.stderr)
    for control in found.matches:
        derivation = derive(state.corpus, control, relations, details)
        sys.stdout.write(
            text.render_control(
                state.corpus,
                derivation,
                placement=relations.placement(control.uid),
                lineage=relations.lineage(control.uid),
                width=args.width,
            )
        )
    return 0


def cmd_export(args) -> int:
    from .render import export

    state = _state()
    payload = _payload(state, args.query)
    body = (
        export.to_csv(state.corpus, payload)
        if args.format == "csv"
        else export.to_markdown(state.corpus, payload)
    )
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(body)
    return 0


def cmd_page(args) -> int:
    from .render import html

    state = _state()
    payload = _payload(state, args.query)
    body = html.render(state.corpus, payload, view=args.view)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(body)
        print("wrote %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(body)
    return 0


def cmd_serve(args) -> int:
    from .serve import main as serve_main

    argv = ["--host", args.host, "--port", str(args.port)]
    if args.open:
        argv.append("--open")
    return serve_main(argv)


def cmd_layout(args) -> int:
    from .render.layout import table

    print(table())
    return 0


def cmd_build(args) -> int:
    from .build import build, summary

    corpus, report = build(verbose=True)
    print(summary(corpus, report))
    if corpus.load_warnings:
        print("\nload warnings (%d):" % len(corpus.load_warnings))
        for warning in corpus.load_warnings:
            print("  - %s" % warning)
    return 0


def cmd_sources(args) -> int:
    try:
        return _cmd_sources(args)
    except (OSError, ValueError) as error:
        print('Source acquisition: %s' % error, file=sys.stderr)
        return 2


def _cmd_sources(args) -> int:
    from pathlib import Path
    from .sources import acquire, describe, status, import_downloads, source_directory
    from collections import Counter

    if args.list:
        for filename, method, detail in describe():
            print("%-9s %s" % (method.upper(), filename))
            print("          %s" % detail)
        return 0

    destination = source_directory(args.destination)
    print('Source folder: %s' % destination, flush=True)
    if args.status:
        rows = status(destination, args.only)
        for row in rows:
            print('%-10s %-9s %s' % (row['state'].upper(), row['method'], row['filename']))
        print(dict(Counter(row['state'] for row in rows)))
        return 1 if any(row['state'] != 'available' for row in rows) else 0
    if args.import_from:
        imported = import_downloads(args.import_from, destination, args.only)
        for name, state, detail in imported:
            print('%-10s %s (from %s)' % (state.upper(), name, detail), flush=True)
        print('%d reviewed files recognised; other files left untouched.' % len(imported), flush=True)
    def progress(row):
        name, state, detail = row
        print('%-10s %s' % (state.upper(), name), flush=True)
        if state in ('manual', 'failed'):
            print('           %s' % detail, flush=True)
    rows = acquire(args.only or None, destination=destination, force=args.force, progress=progress)
    failed = False
    manual = False
    for filename, state, detail in rows:
        failed = failed or state == "failed"
        manual = manual or state == "manual"
    if manual:
        print('\nDownload the remaining manual files, then run: python -m wacc sources --import-from "C:\\path\\to\\downloads"')
    print('Summary: ' + ', '.join('%s=%d' % pair for pair in sorted(Counter(row[1] for row in rows).items())))
    print('Restart a running WACC server to load newly acquired files, or use the Sources page to download and reload together.')
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="wacc", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command")

    search = subs.add_parser("search", help="the crosswalk for a subject")
    search.add_argument("query")
    search.add_argument("--width", type=int, default=78)
    search.set_defaults(func=cmd_search)

    control = subs.add_parser("control", help="one control in full")
    control.add_argument("identifier")
    control.add_argument("--width", type=int, default=78)
    control.set_defaults(func=cmd_control)

    exporter = subs.add_parser("export", help="csv or markdown for a working paper")
    exporter.add_argument("query")
    exporter.add_argument("--format", choices=("csv", "markdown"), default="csv")
    exporter.add_argument("--out")
    exporter.set_defaults(func=cmd_export)

    page = subs.add_parser("page", help="write the results screen to a file")
    page.add_argument("query")
    page.add_argument("--out")
    page.add_argument("--view", choices=("grid", "cards"), default="grid")
    page.set_defaults(func=cmd_page)

    server = subs.add_parser("serve", help="the results screen on localhost")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true",
                        help="open the page in a browser once the corpus has loaded")
    server.set_defaults(func=cmd_serve)

    layout = subs.add_parser("layout", help="column counts at the measured widths")
    layout.set_defaults(func=cmd_layout)

    builder = subs.add_parser("build", help="load the corpus and report")
    builder.set_defaults(func=cmd_build)

    sources = subs.add_parser(
        "sources", help="download public publisher files and explain manual acquisitions"
    )
    sources.add_argument("--list", action="store_true",
                         help="show acquisition methods without downloading")
    sources.add_argument("--status", action="store_true",
                         help="check local files and hashes without downloading")
    sources.add_argument("--import-from", metavar="FOLDER",
                         help="copy recognised reviewed downloads into the cache, then acquire remaining files")
    sources.add_argument("--only", action="append", metavar="FILENAME",
                         help="acquire one named source; repeat to acquire several")
    sources.add_argument("--destination",
                         help="source directory (defaults to WACC_SOURCES or sources/files)")
    sources.add_argument("--force", action="store_true",
                         help="download again even when reviewed bytes are already present")
    sources.set_defaults(func=cmd_sources)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
