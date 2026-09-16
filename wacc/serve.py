"""Serve the Control workspace and source browser on the local computer.

The Sources page can acquire reviewed public files on request. The server binds to
127.0.0.1 by default because some corpus material is approved only for this private,
non-commercial project.

Routes provide complete web pages, detail panels and downloadable exports. Rendering stays
in Python so the web and test outputs use the same wording and escaping rules.
"""

import argparse
import json
import secrets
import socket
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from email.parser import BytesParser
from email.policy import default as email_policy

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


def _handler(initial_state: State):
    from .source_workspace import AcquisitionJob, render as render_sources
    from . import department_assessments as assessments, department_workspace, telemetry, telemetry_workspace
    states = [initial_state]
    assessment_store = assessments.Store()
    assessment_token = secrets.token_urlsafe(32)
    validation_store = telemetry.ValidationStore(assessment_store)

    def reload_corpus():
        replacement = State()
        states[0] = replacement

    acquisition = AcquisitionJob(reload_corpus)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, body: str, content_type: str, filename: Optional[str] = None,
                  code: int = 200):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", content_type + ('; charset=utf-8' if isinstance(body, str) else ''))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
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
            state = states[0]
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == '/sources':
                return self._send(render_sources(acquisition), 'text/html')
            params = urllib.parse.parse_qs(parsed.query)
            if parsed.path.startswith('/assessments/validation'):
                try:
                    if parsed.path == '/assessments/validation':
                        return self._send(telemetry_workspace.render(assessment_store, assessment_token, params), 'text/html')
                    if parsed.path == '/assessments/validation/example':
                        year = (params.get('year') or ['2025'])[0]
                        if year not in ('2023', '2024', '2025'): raise assessments.AssessmentError('Choose 2023, 2024 or 2025.')
                        return self._send(telemetry.example_bundle(int(year)), 'application/json', f'silly-walks-{year}-telemetry.json')
                    if parsed.path == '/assessments/validation/guide':
                        return self._send((assessments.ROOT/'docs/telemetry-validation.md').read_text(encoding='utf-8'), 'text/plain')
                    if parsed.path == '/assessments/validation/queries':
                        return self._send((assessments.ROOT/'examples/telemetry/export-sentinel.kql').read_text(encoding='utf-8'), 'text/plain', 'export-sentinel.kql')
                    if parsed.path == '/assessments/validation/report':
                        report = validation_store.get((params.get('run') or [''])[0])
                        if not report: return self.send_error(404, 'no such validation run')
                        return self._send(json.dumps(report, ensure_ascii=False, indent=2), 'application/json', 'validation-report.json')
                    return self.send_error(404, 'no such validation page')
                except assessments.AssessmentError as exc:
                    return self._send(str(exc), 'text/plain', code=400)
                except OSError:
                    return self._send('Validation files are unavailable.', 'text/plain', code=500)
            if parsed.path == '/assessments':
                try:
                    notice = 'Assessment workbooks imported.' if params.get('imported') else ''
                    return self._send(department_workspace.render(assessment_store, assessment_token, params, notice), 'text/html')
                except assessments.AssessmentError as exc:
                    return self._send(str(exc), 'text/plain', code=500)
            if parsed.path.startswith('/assessments/download/'):
                name = parsed.path.rsplit('/', 1)[-1]
                if name not in assessments.DOWNLOADS:
                    return self.send_error(404, 'no such workbook')
                path = assessments.ROOT / 'examples/assessments' / name
                if not path.is_file():
                    return self.send_error(404, 'example workbook is missing')
                return self._send(path.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', name)
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

        def do_POST(self):
            if self.path in ('/assessments/validation/import', '/assessments/validation/demo', '/assessments/validation/review'):
                return self._validate_assessment()
            if self.path in ('/assessments/import', '/assessments/examples'):
                return self._import_assessments()
            if self.path != '/sources/acquire':
                return self.send_error(404, 'no such action')
            try:
                size = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                return self.send_error(400, 'invalid request length')
            if not 0 < size <= 4096:
                return self.send_error(400, 'invalid request length')
            params = urllib.parse.parse_qs(self.rfile.read(size).decode('utf-8', errors='replace'))
            if not acquisition.start((params.get('token') or [''])[0]):
                return self.send_error(403, 'reload the Sources page and try again')
            self.send_response(303)
            self.send_header('Location', '/sources')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def _validate_assessment(self):
            try:
                try: size = int(self.headers.get('Content-Length', '0'))
                except ValueError: size = 0
                if not 0 < size <= telemetry.MAX_BYTES + 65536:
                    raise assessments.AssessmentError('Select files totalling less than 20 MB.')
                origin = self.headers.get('Origin')
                if origin and urllib.parse.urlparse(origin).netloc != self.headers.get('Host'):
                    raise assessments.AssessmentError('Reload the validation page before submitting.')
                body = self.rfile.read(size)
                if len(body) != size: raise assessments.AssessmentError('The upload was incomplete.')
                kind = self.headers.get('Content-Type', '')
                if not kind.startswith('multipart/form-data;'):
                    raise assessments.AssessmentError('Use the form on the validation page.')
                message = BytesParser(policy=email_policy).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
                if not message.is_multipart() or message.defects:
                    raise assessments.AssessmentError('Malformed file upload.')
                fields = {}; files = []
                for part in message.iter_parts():
                    field = part.get_param('name', header='content-disposition')
                    data = part.get_payload(decode=True)
                    if data is None: raise assessments.AssessmentError('Nested uploads are not supported.')
                    if field == 'files' and part.get_filename(): files.append((part.get_filename(), data))
                    else:
                        if field in fields or len(data)>8192: raise assessments.AssessmentError('Invalid form fields.')
                        fields[field] = data.decode('utf-8', errors='replace')
                if not secrets.compare_digest(fields.get('token', '').encode(), assessment_token.encode()):
                    raise assessments.AssessmentError('Reload the validation page before submitting.')
                if self.path.endswith('/review'):
                    report = validation_store.review(fields.get('run', ''), fields.get('finding', ''), fields.get('decision', ''), fields.get('reviewer', ''), fields.get('note', ''))
                else:
                    key = fields.get('assessment', '')
                    if self.path.endswith('/demo'):
                        record = next((a for a in assessment_store.all() if a['key'] == key), None)
                        if not record or record['department'] != 'Department of Silly Walks' or record['year'] not in (2023, 2024, 2025):
                            raise assessments.AssessmentError('Select an imported Silly Walks example assessment.')
                        files = telemetry.example_files(record['year'])
                    report = validation_store.import_files(files, key)
                location = '/assessments/validation?' + urllib.parse.urlencode({'run':report['id']})
                return self._send(json.dumps({'location':location}), 'application/json')
            except assessments.AssessmentError as exc:
                return self._send(json.dumps({'error':str(exc)}), 'application/json', code=400)
            except OSError:
                return self._send(json.dumps({'error':'Evidence storage is unavailable. Check folder permissions and free space.'}), 'application/json', code=500)

        def _import_assessments(self):
            try:
                origin = self.headers.get('Origin')
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    size = 0
                if not 0 < size <= 20 * 1024 * 1024:
                    raise assessments.AssessmentError('Select files totalling less than 20 MB.')
                body = self.rfile.read(size)
                if len(body) != size:
                    raise assessments.AssessmentError('The upload was incomplete. Try again.')
                if origin and urllib.parse.urlparse(origin).netloc != self.headers.get('Host'):
                    raise assessments.AssessmentError('Reload the Assessments page before importing.')
                if self.path == '/assessments/examples':
                    params = urllib.parse.parse_qs(body.decode('utf-8', errors='replace'))
                    token = (params.get('token') or [''])[0]
                    replace = False
                    files = [(name, (assessments.ROOT/'examples/assessments'/name).read_bytes()) for name in assessments.EXAMPLES]
                else:
                    kind = self.headers.get('Content-Type', '')
                    if not kind.startswith('multipart/form-data;'):
                        raise assessments.AssessmentError('Use the file picker on the Assessments page.')
                    message = BytesParser(policy=email_policy).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
                    if not message.is_multipart() or message.defects:
                        raise assessments.AssessmentError('The file upload is malformed.')
                    token=''; replace=False; files=[]
                    for part in message.iter_parts():
                        field = part.get_param('name', header='content-disposition')
                        data = part.get_payload(decode=True)
                        if data is None:
                            raise assessments.AssessmentError('Nested uploads are not supported.')
                        if field == 'token': token=data.decode('ascii',errors='replace')
                        elif field == 'replace': replace=data == b'1'
                        elif field == 'files' and part.get_filename(): files.append((part.get_filename(),data))
                    if len(files)>10:
                        raise assessments.AssessmentError('Import no more than ten workbooks at once.')
                if not secrets.compare_digest(token.encode('utf-8'),assessment_token.encode('ascii')):
                    raise assessments.AssessmentError('Reload the Assessments page before importing.')
                imported = assessment_store.import_files(files,replace=replace)
                location = '/assessments?' + urllib.parse.urlencode({'department':imported[0]['department'],'imported':'1'})
                if self.path == '/assessments/examples':
                    self.send_response(303)
                    self.send_header('Location',location)
                    self.send_header('Content-Length','0')
                    self.end_headers()
                else:
                    return self._send(json.dumps({'location':location}), 'application/json')
            except assessments.AssessmentError as exc:
                return self._send(json.dumps({'error':str(exc)}), 'application/json', code=400)
            except OSError:
                return self._send(json.dumps({'error':'Assessment storage is unavailable. Check folder permissions and free space.'}), 'application/json', code=500)

        def _panel(self, uid: str):
            state = states[0]
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
    from .framework_families import count as family_count
    loaded={c.framework_key for c in state.corpus.controls.values()}
    print("WACC on %s  (%d source records, %d framework families). Ctrl-C to stop."
          % (url, len(state.corpus.controls), family_count(loaded)))
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
