"""Follow actual published and derived links through the local HTTP server."""
import html
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest
import urllib.parse
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc.serve import State, _handler


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []
    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            href = dict(attrs).get('href', '')
            if href.startswith('/?'):
                self.hrefs.append(href)


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = State()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), _handler(cls.state))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = 'http://127.0.0.1:%d' % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as response:
            self.assertEqual(response.status, 200)
            return response.read().decode('utf-8')

    def test_follow_every_ism_1507_link_to_exact_control(self):
        panel = self.get('/control?uid=ism%3Aism-1507')
        parsed = Links()
        parsed.feed(panel)
        lineage = self.state.relations.lineage('ism:ism-1507')
        targets = {r.other.uid for b in lineage.bands for r in b.relations}
        self.assertIn('Linked — published', panel)
        self.assertIn('Linked — derived', panel)
        self.assertTrue(any(uid.startswith('aescsf:access') for uid in targets))
        self.assertTrue(any(uid.startswith('cis-controls:') for uid in targets))
        self.assertEqual(len(parsed.hrefs), len(targets))
        visited = set()
        for href in parsed.hrefs:
            uid = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)['q'][0]
            with self.subTest(uid=uid):
                page = self.get(href)
                control = self.state.corpus.control(uid)
                self.assertIsNotNone(control)
                self.assertEqual([c.uid for c in self.state.payload(uid).controls], [uid])
                self.assertEqual(page.count('class="cardcol"'), 1)
                self.assertIn('data-panel="%s"' % html.escape(uid, quote=True), page)
                self.assertIn('data-focus-fw="%s"' % control.framework_key, page)
                self.assertIn(html.escape(' '.join(control.text.split())), page)
                self.get('/control?' + urllib.parse.urlencode({'uid': uid}))
                visited.add(uid)
        self.assertEqual(visited, targets)

    def test_exact_control_link_exports_same_control(self):
        data = self.get('/export.csv?' + urllib.parse.urlencode({'q': 'cis-controls:5.4'}))
        self.assertIn('5.4', data)
        self.assertIn('Restrict Administrator', data)


if __name__ == '__main__':
    unittest.main()
