"""Regressions for the September 2026 code audit, including real HTTP listeners."""
import csv
import errno
import hashlib
import http.client
import io
from contextlib import contextmanager, redirect_stdout
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socket
import sys
import shutil
import threading
import unittest
import uuid
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc import build, sources
from wacc.io.docx import Document, Paragraph
from wacc.loaders import cis
from wacc.lookup import Status
from wacc.model import Corpus, Control, ObligationStrength
from wacc.registry import FRAMEWORKS_BY_KEY
from wacc.render import export, html, text
from wacc.serve import State, _handler, bind_server, serve, IPv6LocalHTTPServer


class ExportLinks(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.links = {}
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        target = values.get('href', values.get('data-copy', ''))
        if urlsplit(target).path in ('/export.csv', '/export.md', '/exec.md', '/plan.md'):
            self.links[urlsplit(target).path] = target


def response(host, port, path='/'):
    client = http.client.HTTPConnection(host, port, timeout=15)
    try:
        client.request('GET', path)
        result = client.getresponse()
        return result.status, result.read().decode('utf-8')
    finally:
        client.close()


def start(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


@contextmanager
def fixture_directory():
    # Normal workspace permissions also work in Windows restricted test accounts.
    folder = ROOT / ('.wacc-audit-test-' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        assert folder.resolve().parent == ROOT.resolve()
        shutil.rmtree(folder)


class CorpusAndSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = State()
        cls.server = bind_server('127.0.0.1', 0, _handler(cls.state))
        cls.thread = start(cls.server)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_unnumbered_sections_and_mandatory_continuations_survive(self):
        corpus = self.state.corpus
        for uid in ('soci-act:s 30ac', 'soci-act:s 30ae', 'soci-act:s 30cd', 'cirmp-rules:s 6'):
            with self.subTest(uid=uid):
                control = corpus.control(uid)
                self.assertTrue(control.text.strip())
                self.assertFalse(control.attributes.get('structural'))
        for uid in ('soci-act:s 30bc.1', 'soci-act:s 30bd.1'):
            self.assertIn('the entity must:', corpus.control(uid).text)
            self.assertEqual(corpus.control(uid).obligation, ObligationStrength.MANDATORY)

    def test_legislative_paragraphs_match_publisher_sections(self):
        # Compare full source bodies, including multiple unnumbered paragraphs.
        for key in ('soci-act', 'cirmp-rules'):
            blocks = Document(str(ROOT / 'sources/files' / (key + '-latest.docx'))).blocks()
            uid = section = None
            expected = {}
            for block in blocks:
                if not isinstance(block, Paragraph) or not block.text:
                    continue
                if block.style.startswith(('ActHead 2', 'ActHead 3', 'ActHead 5', 'ActHead 6')):
                    uid = None
                    section = block.text.split()[0] if block.style.startswith(('ActHead 5', 'ActHead 6')) else None
                    if section and not section[0].isdigit():
                        section = None
                elif block.style == 'subsection' and section:
                    if block.text.startswith('('):
                        number, body = block.text.split(')', 1)
                        uid = key + ':s ' + section.lower() + '.' + number[1:].lower()
                    else:
                        uid, body = key + ':s ' + section.lower(), block.text
                    expected.setdefault(uid, []).append(body.strip())
                elif uid and block.style in ('subsection2', 'paragraph', 'paragraph(sub)', 'Definition', 'Penalty'):
                    expected[uid].append(block.text)
            for uid, paragraphs in expected.items():
                with self.subTest(uid=uid):
                    self.assertEqual(self.state.corpus.control(uid).text, '\n'.join(paragraphs))

    def test_cis_repeated_rows_keep_their_safeguards(self):
        def strategies(identifier):
            c = self.state.corpus.control('cis-controls:' + identifier)
            return {tag['strategy'] for tag in c.publisher_tags.get('essential_eight', [])}
        self.assertEqual(strategies('6.5'), {'Restricting Administrative Privileges', 'Multi-factor Authentication'})
        self.assertEqual(strategies('6.6'), set())
        self.assertEqual(strategies('7.3'), {'Patch OS Systems'})
        self.assertEqual(strategies('7.4'), {'Patch Applications'})
        self.assertFalse(any('cis mapping' in warning for warning in self.state.corpus.load_warnings))

    def test_cis_numeric_collision_uses_title_not_mapping_row_order(self):
        corpus = Corpus()
        corpus.add_framework(FRAMEWORKS_BY_KEY['cis-controls'])
        for identifier, title in (('3.1', 'First safeguard'), ('3.10', 'Tenth safeguard')):
            corpus.add_control(Control('cis-controls', identifier, 'Requirement', title=title, depth=1))
        header = ['CIS Control', 'CIS Safeguard', 'Title', 'Relationship', 'Security Control']
        rows = [['3', '3.1', 'Tenth safeguard', 'Subset', 'Strategy A'],
                ['3', '3.1', 'First safeguard', 'Subset', 'Strategy B'],
                ['3', '3.1', 'Tenth safeguard', 'Superset', 'Strategy C']]
        with patch.object(cis, 'Workbook') as book:
            book.return_value.table.return_value = (header, rows)
            cis.load_essential_eight_mapping(corpus, FRAMEWORKS_BY_KEY['cis-controls'], 'fixture.xlsx')
        self.assertEqual([r['strategy'] for r in corpus.control('cis-controls:3.10').publisher_tags['essential_eight']], ['Strategy A', 'Strategy C'])
        self.assertEqual([r['strategy'] for r in corpus.control('cis-controls:3.1').publisher_tags['essential_eight']], ['Strategy B'])

    def test_scoped_aliases_are_not_masked_by_another_framework(self):
        lookup = self.state.lookup
        result = lookup.find('asd-principles:gov 1')
        self.assertEqual([c.uid for c in result.matches], ['asd-principles:gov-1'])
        result = lookup.find('PSPF 10')
        self.assertIn('pspf:req 10', {c.uid for c in result.matches})
        self.assertTrue(all(c.framework_key == 'pspf' for c in result.matches))
        self.assertEqual(lookup.find('10').matched_form, '10')

    def test_withdrawn_identifiers_show_replacements_and_export_notice(self):
        for query in ('csf:ID.SC-01', 'csf:ID.AM-06'):
            found = self.state.lookup.find(query)
            self.assertEqual(found.status, Status.WITHDRAWN)
            expected = {c.uid for redirect in found.redirects for c in redirect.resolved}
            payload = self.state.payload(query)
            self.assertEqual({c.uid for c in payload.controls}, expected)
            code, page = response('127.0.0.1', self.server.server_port, '/?' + urlencode({'q': query, 'view': 'cards'}))
            self.assertEqual(code, 200)
            self.assertIn('was withdrawn', page)
            self.assertIn('Replacement controls:', page)
            for uid in expected:
                target = '/?' + urlencode({'q': uid, 'view': 'cards'})
                self.assertEqual(response('127.0.0.1', self.server.server_port, target)[0], 200)
            self.assertIn('was withdrawn', export.to_csv(self.state.corpus, payload))
            self.assertIn('was withdrawn', export.to_markdown(self.state.corpus, payload))

    def test_hidden_matches_are_not_silent_frameworks(self):
        # Keep all matches while deliberately displaying none to exercise every renderer.
        from wacc.analysis import analyse
        control = self.state.corpus.control('ism:ism-1507')
        payload = analyse(self.state.corpus, 'privileged access', [control], display=[])
        self.assertNotIn('ism', {f.key for f in payload.frameworks_silent})
        cards = html.render(self.state.corpus, payload, view='cards')
        self.assertIn('0 shown of 1 read', cards)
        self.assertIn('1 matching controls are outside', cards)
        self.assertIn('nothing in the shown set', html.render(self.state.corpus, payload, view='grid'))
        self.assertIn('and 1 more', text.render(self.state.corpus, payload))
        silent_rows = list(csv.reader(io.StringIO(export.to_csv(self.state.corpus, payload))))
        self.assertFalse(any(len(row) > 2 and row[2] == 'ISM' for row in silent_rows))

    def test_all_export_actions_keep_the_selected_limit(self):
        for limit in (10, 50):
            payload = self.state.payload('privileged access', limit)
            page = html.render(self.state.corpus, payload, limit=limit)
            links = ExportLinks(page).links
            self.assertEqual(len(links), 4)
            for path, target in links.items():
                with self.subTest(limit=limit, path=path):
                    self.assertEqual(parse_qs(urlsplit(target).query)['limit'], [str(limit)])
                    code, body = response('127.0.0.1', self.server.server_port, target)
                    self.assertEqual(code, 200)
                    expected = {
                        '/export.csv': lambda: export.to_csv(self.state.corpus, payload),
                        '/export.md': lambda: export.to_markdown(self.state.corpus, payload),
                        '/exec.md': lambda: export.risk_summary(self.state.corpus, payload, self.state.risks(self.state.derivations(payload))),
                        '/plan.md': lambda: export.test_plan(self.state.corpus, payload, self.state.derivations(payload)),
                    }[path]()
                    self.assertEqual(body, expected)


class SourceAndServerTests(unittest.TestCase):
    def test_import_into_mixed_nested_cache_is_loaded(self):
        name = 'aescsf-framework-core.xlsx'
        body = (ROOT / 'sources/files' / name).read_bytes()
        entry = dict(filename=name, sha256=hashlib.sha256(body).hexdigest())
        with fixture_directory() as temporary:
            folder = Path(temporary)
            cache = folder / 'cache'
            (cache / 'documents').mkdir(parents=True)
            downloads = folder / 'downloads'
            downloads.mkdir()
            (downloads / 'renamed.xlsx').write_bytes(body)
            with patch.object(sources, 'load_catalogue', return_value=({name: entry}, {name: {'method': 'manual'}})):
                self.assertEqual(sources.import_downloads(downloads, cache)[0][1], 'imported')
                self.assertEqual(sources.status(cache)[0]['state'], 'available')
            with patch.object(build, 'RAW', str(cache)):
                self.assertEqual(Path(build._doc(name)), cache / name)
                corpus, report = build.build(False)
                self.assertEqual(len(corpus.controls_for('aescsf')), 408)
                self.assertNotIn('aescsf', report.skipped)
            (cache / name).rename(cache / 'documents' / name)
            with patch.object(build, 'RAW', str(cache)):
                self.assertEqual(Path(build._doc(name)), sources.local_path(cache, name))

    @staticmethod
    def handler(message):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(message.encode())
        return Handler

    def test_two_instances_bind_distinct_ports_and_serve_their_own_pages(self):
        servers, threads = [], []
        try:
            first = bind_server('127.0.0.1', 0, self.handler('first'))
            servers.append(first)
            threads.append(start(first))
            second = bind_server('127.0.0.1', first.server_port, self.handler('second'))
            servers.append(second)
            threads.append(start(second))
            self.assertNotEqual(first.server_port, second.server_port)
            for server, expected in ((first, 'first'), (second, 'second')):
                self.assertEqual(response('127.0.0.1', server.server_port), (200, expected))
            with self.assertRaises(OSError):
                bind_server('127.0.0.1', first.server_port, self.handler('third'), span=1)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()

    def test_ipv6_listener_and_advertised_url(self):
        if not socket.has_ipv6:
            self.skipTest('IPv6 is unavailable on this host')
        try:
            server = bind_server('::1', 0, self.handler('IPv6'))
        except OSError as error:
            if error.errno in (errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL):
                self.skipTest('IPv6 loopback is disabled on this host')
            raise
        thread = start(server)
        try:
            self.assertEqual(response('::1', server.server_port), (200, 'IPv6'))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        with patch('wacc.serve.State') as state, patch.object(IPv6LocalHTTPServer, 'serve_forever', side_effect=KeyboardInterrupt), redirect_stdout(io.StringIO()) as output:
            state.return_value.corpus.controls = {}
            serve('::1', 0, verbose=False)
        self.assertIn('http://[::1]:', output.getvalue())


if __name__ == '__main__':
    unittest.main()
