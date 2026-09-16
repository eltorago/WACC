"""Serve the Control workspace and source browser on the local computer.

The server reads data already on disk and does not download anything. It binds to
127.0.0.1 by default because some corpus material is approved only for this private,
non-commercial project.

Routes provide complete web pages, detail panels and downloadable exports. Rendering stays
in Python so the web and test outputs use the same wording and escaping rules.
"""

import argparse
import socket
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional

from .analysis import analyse, gather
from . import control_workspace
from .build import build
from .derive import DetailIndex, derive
from .lookup import IdentifierIndex, Status, looks_like_identifier
from .relate import Relations
from .render import export, html
from .search import SearchIndex

DISPLAY = 25


class State:
    """Built once at start-up. A rebuild per request would take four seconds each time."""

    def __init__(self, verbose: bool = False) -> None:
        self.corpus, self.report = build(verbose=verbose)
        self.index = SearchIndex(self.corpus)
        self.lookup = IdentifierIndex(self.corpus)
        self.relations = Relations(self.corpus)
        self.details = DetailIndex(self.corpus, self.index.weight_of)

    def payload(self, query: str, limit: int = DISPLAY):
        """The one payload every renderer reads.

        An identifier goes to exact lookup first, because typing AC-6(5) is a request for
        one control and a ranked list of things that mention privileged accounts is a
        different question with a worse answer.
        """
        query = (query or "").strip()
        if not query:
            return analyse(self.corpus, "", [], display=[])
        # Links use corpus UIDs, so identical publisher identifiers cannot collide.
        direct = self.corpus.control(query)
        if direct is not None:
            return analyse(self.corpus, query, [direct], evidence="exact control link",
                           display=[direct])
        if looks_like_identifier(query):
            found = self.lookup.find(query)
            if found.status in (Status.UNIQUE, Status.AMBIGUOUS):
                controls = list(found.matches)
                return analyse(
                    self.corpus, query, controls, evidence="exact identifier lookup",
                    display=controls,
                )
        deep = gather(self.corpus, self.index, query)
        shown = [hit.control for hit in self.index.search(query, limit=limit).hits]
        return analyse(self.corpus, query, deep, display=shown)

    def derivations(self, payload) -> Dict[str, object]:
        """Test procedure and risk statement for everything on screen.

        Derived per request rather than at start-up. Twenty-five controls cost about
        twenty milliseconds, and pre-deriving thousands would spend several seconds on the
        5,296 nobody asked for.
        """
        out: Dict[str, object] = {}
        for control in payload.controls:
            out[control.uid] = derive(
                self.corpus, control, self.relations, self.details
            )
        return out

    def risks(self, derivations: Dict[str, object]) -> Dict[str, object]:
        return {
            uid: d.risk for uid, d in derivations.items() if getattr(d, "risk", None)
        }

    def breadcrumbs(self, payload) -> Dict[str, list]:
        out: Dict[str, list] = {}
        for control in payload.controls:
            placement = self.relations.placement(control.uid)
            if placement is not None:
                out[control.uid] = placement.breadcrumb
        return out


def _limit(params) -> int:
    """A limit from the query string, clamped to what the page offers."""
    try:
        wanted = int((params.get("limit") or [str(DISPLAY)])[0])
    except ValueError:
        return DISPLAY
    return wanted if wanted in html.LIMIT_CHOICES else DISPLAY


def _handler(state: State):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, body: str, content_type: str, filename: Optional[str] = None,
                  code: int = 200):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "%s; charset=utf-8" % content_type)
            self.send_header("Content-Length", str(len(data)))
            # The page draws a fragment this server sent into the document. Saying so
            # stops a browser guessing the type of anything it did not expect.
            self.send_header("X-Content-Type-Options", "nosniff")
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
            limit = _limit(params)

            if parsed.path == "/library/export.csv":
                return self._send(control_workspace.export_csv(params, state.corpus), "text/csv", "control-mappings.csv")
            if parsed.path == "/library" or (parsed.path in ("/", "/index.html") and not params):
                return self._send(control_workspace.render(state.corpus, params), "text/html")

            if parsed.path == "/frameworks":
                from .framework_review import render
                return self._send(render(state.corpus), "text/html")

            if parsed.path == "/control":
                return self._panel((params.get("uid") or [""])[0])

            payload = state.payload(query, limit)
            if parsed.path == "/export.csv":
                return self._send(
                    export.to_csv(state.corpus, payload), "text/csv", "wacc.csv"
                )
            if parsed.path == "/export.md":
                return self._send(
                    export.to_markdown(state.corpus, payload), "text/markdown", "wacc.md"
                )
            if parsed.path == "/exec.md":
                derivations = state.derivations(payload)
                return self._send(
                    export.risk_summary(
                        state.corpus, payload, state.risks(derivations)
                    ),
                    "text/markdown", "wacc-risk-summary.md",
                )
            if parsed.path == "/plan.md":
                return self._send(
                    export.test_plan(
                        state.corpus, payload, state.derivations(payload)
                    ),
                    "text/markdown", "wacc-test-plan.md",
                )
            if parsed.path in ("/", "/index.html"):
                view = (params.get("view") or ["cards"])[0]
                derivations = state.derivations(payload) if view == "cards" else {}
                return self._send(
                    html.render(
                        state.corpus, payload, view=view, limit=limit,
                        risks=state.risks(derivations),
                        breadcrumbs=state.breadcrumbs(payload) if view == "cards" else {},
                    ),
                    "text/html",
                )
            self.send_error(404, "no such page")

        def _panel(self, uid: str):
            control = state.corpus.control(uid)
            if control is None:
                return self._send(
                    '<p class="note">No control with that identifier is loaded.</p>',
                    "text/html", code=404,
                )
            derivation = derive(state.corpus, control, state.relations, state.details)
            return self._send(
                html.control_panel(
                    state.corpus,
                    derivation,
                    placement=state.relations.placement(uid),
                    lineage=state.relations.lineage(uid),
                ),
                "text/html",
            )

    return Handler


def free_port(preferred: int, host: str = "127.0.0.1", span: int = 20) -> int:
    """The first free port at or after the preferred one.

    A second copy of the tool on the same machine is a normal thing to want and refusing
    to start because 8765 is taken is not a useful answer. Returns the preferred port if
    nothing in the span is free, so the bind failure is reported by the bind rather than
    swallowed here.
    """
    for port in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
                return port
            except OSError:
                continue
    return preferred


def serve(host: str = "127.0.0.1", port: int = 8765, verbose: bool = True,
          open_browser: bool = False) -> None:
    state = State(verbose=verbose)
    port = free_port(port, host)
    server = ThreadingHTTPServer((host, port), _handler(state))
    url = "http://%s:%d/" % (host, port)
    print(
        "WACC on %s  (%d controls, %d frameworks). Ctrl-C to stop."
        % (url, len(state.corpus.controls), len(state.corpus.frameworks))
    )
    if open_browser:
        import threading

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
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
    parser.add_argument("--open", action="store_true",
                        help="open the page in a browser once the corpus has loaded")
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        # Refused rather than warned: the corpus holds import-only publisher text.
        print(
            "refusing to bind to %s. This serves import-only text and is localhost only."
            % args.host,
            file=sys.stderr,
        )
        return 2
    start(args.host, args.port, open_browser=args.open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
