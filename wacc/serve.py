"""A local server for the results screen. Standard library, localhost, no network.

Bound to 127.0.0.1 by default and never to 0.0.0.0, because the corpus holds import-only
text that must not be redistributable, and a tool that serves it to the LAN by default is
redistributing it. Nothing here fetches anything; the page is written from the corpus
already on disk.
"""

import argparse
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Tuple

from .analysis import analyse, gather
from .build import build
from .lookup import IdentifierIndex, Status, looks_like_identifier
from .render import export, html
from .search import SearchIndex

DISPLAY = 25


class State:
    """Built once at start-up. A rebuild per request would take half a second each time."""

    def __init__(self, verbose: bool = False) -> None:
        self.corpus, self.report = build(verbose=verbose)
        self.index = SearchIndex(self.corpus)
        self.lookup = IdentifierIndex(self.corpus)

    def payload(self, query: str):
        """The one payload every renderer reads.

        An identifier goes to exact lookup first, because typing AC-6(5) is a request for
        one control and a ranked list of things that mention privileged accounts is a
        different question with a worse answer.
        """
        query = (query or "").strip()
        if not query:
            return analyse(self.corpus, "", [], display=[])
        if looks_like_identifier(query):
            found = self.lookup.find(query)
            if found.status in (Status.UNIQUE, Status.AMBIGUOUS):
                controls = list(found.matches)
                return analyse(
                    self.corpus, query, controls, evidence="exact identifier lookup",
                    display=controls,
                )
        deep = gather(self.corpus, self.index, query)
        shown = [hit.control for hit in self.index.search(query, limit=DISPLAY).hits]
        return analyse(self.corpus, query, deep, display=shown)


def _handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, body: str, content_type: str, filename: Optional[str] = None):
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "%s; charset=utf-8" % content_type)
            self.send_header("Content-Length", str(len(data)))
            if filename:
                self.send_header(
                    "Content-Disposition", 'attachment; filename="%s"' % filename
                )
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 - http.server's interface
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            query = (params.get("q") or [""])[0]
            payload = state.payload(query)
            if parsed.path == "/export.csv":
                self._send(
                    export.to_csv(state.corpus, payload), "text/csv", "wacc.csv"
                )
            elif parsed.path == "/export.md":
                self._send(
                    export.to_markdown(state.corpus, payload), "text/markdown", "wacc.md"
                )
            elif parsed.path in ("/", "/index.html"):
                self._send(html.render(state.corpus, payload), "text/html")
            else:
                self.send_error(404, "no such page")

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, verbose: bool = True) -> None:
    state = State(verbose=verbose)
    server = HTTPServer((host, port), _handler(state))
    print(
        "WACC on http://%s:%d  (%d controls, %d frameworks). Ctrl-C to stop."
        % (host, port, len(state.corpus.controls), len(state.corpus.frameworks))
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()


def main(argv=None, start=None) -> int:
    """Parse, refuse a non-local host, then serve.

    `start` exists so the refusal can be tested without a server being started. Without
    it the test for the refusal cannot fail: if the guard is ever removed, the call
    blocks in serve_forever and the suite hangs instead of reporting.
    """
    start = serve if start is None else start
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # Refused rather than warned: the corpus holds import-only publisher text.
        print(
            "refusing to bind to %s. This serves import-only text and is localhost only."
            % args.host,
            file=sys.stderr,
        )
        return 2
    start(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
