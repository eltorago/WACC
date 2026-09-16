"""Acquisition must preserve reviewed files and make incomplete setup visible."""
import hashlib
import json
from pathlib import Path
import shutil
import uuid
import threading
import unittest
import sys
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc import sources
from wacc.source_workspace import AcquisitionJob, render


class SourceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / ('.wacc-source-test-' + uuid.uuid4().hex)
        self.root.mkdir()
        self.body = b'reviewed source bytes'
        self.entry = dict(filename='source.pdf', sha256=hashlib.sha256(self.body).hexdigest())
        self.method = dict(method='automatic', urls=['https://publisher.test/source.pdf'])

    def tearDown(self):
        shutil.rmtree(self.root)

    def catalogue(self):
        return patch.object(sources, 'load_catalogue', return_value=({'source.pdf': self.entry}, {'source.pdf': self.method}))

    def test_environment_destination_and_nested_existing_file(self):
        nested = self.root / 'documents' / 'source.pdf'
        nested.parent.mkdir(); nested.write_bytes(self.body)
        with self.catalogue(), patch.dict('os.environ', {'WACC_SOURCES': str(self.root)}), patch.object(sources, '_read') as fetch:
            self.assertEqual(sources.source_directory(), self.root.resolve())
            self.assertEqual(sources.status()[0]['state'], 'available')
            self.assertEqual(sources.acquire()[0][1], 'available')
            fetch.assert_not_called()
        nested.write_bytes(b'changed')
        with self.catalogue():
            self.assertEqual(sources.status(self.root)[0]['state'], 'changed')

    def test_renamed_manual_download_import_and_unmatched_files_untouched(self):
        downloads = self.root / 'downloads'; downloads.mkdir()
        original = downloads / 'renamed-by-browser (1).pdf'; original.write_bytes(self.body)
        unknown = downloads / 'unreviewed.pdf'; unknown.write_bytes(b'other edition')
        target = self.root / 'cache'
        with self.catalogue():
            rows = sources.import_downloads(downloads, target)
        self.assertEqual(rows[0][0:2], ('source.pdf', 'imported'))
        self.assertEqual(original.read_bytes(), self.body)
        self.assertEqual(unknown.read_bytes(), b'other edition')
        self.assertEqual(list(target.iterdir()), [target / 'source.pdf'])

    def test_changed_html_is_not_followed_or_installed(self):
        entry = dict(self.entry, filename='source.html')
        (self.root / 'source.html').write_bytes(self.body)
        with patch.object(sources, '_read', return_value=(b'<html><a href="other.html">Next</a></html>', 'text/html', 'https://publisher.test/source.html')) as fetch:
            result = sources.acquire_one(entry, self.method, self.root, force=True)
        self.assertEqual(result[0], 'failed')
        self.assertIn('SHA-256', result[1])
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual((self.root / 'source.html').read_bytes(), self.body)

    def test_oag_verification_ignores_only_material_outside_report(self):
        def page(nonce='one', wording='Original report', link='report.pdf'):
            return ('<script nonce="%s"></script><div class="new-report-header"><h1>Report title</h1><p>Date</p><a href="%s">Download</a></div><div class="new-report__body"><h2>Findings</h2><p>%s</p><p>Recommendation</p></div><form>Rotating form value %s</form>' % (nonce, link, wording, nonce)).encode()
        body = page()
        entry = dict(filename='oag-test.html', source_url='https://audit.wa.gov.au/report/',
                     sha256=hashlib.sha256(body).hexdigest(),
                     content_verification=dict(method='oag-report-v1', sha256=sources.report_digest(body)))
        self.assertTrue(sources.matches_review(entry, page('two')))
        self.assertFalse(sources.matches_review(entry, page(wording='Changed finding')))
        self.assertFalse(sources.matches_review(entry, page(link='other.pdf')))
        self.assertFalse(sources.matches_review(entry, page() + page()))
        self.assertFalse(sources.matches_review(entry, b'<html>Access denied</html>'))

    def test_landing_page_discovery_is_bounded_and_same_publisher(self):
        body = b'<html><a href="https://other.test/source.pdf">Other</a>' + b''.join(('<a href="%d.pdf">Doc</a>' % i).encode() for i in range(40)) + b'</html>'
        links = sources._candidate_links(body, 'https://publisher.test/', 'source.pdf')
        self.assertEqual(len(links), 6)
        self.assertTrue(all(x.startswith('https://publisher.test/') for x in links))
        with patch.object(sources, '_read', return_value=(body, 'text/html', 'https://publisher.test/')) as fetch:
            self.assertEqual(sources.acquire_one(self.entry, self.method, self.root)[0], 'failed')
            self.assertLessEqual(fetch.call_count, 7)

    def test_transient_http_errors_retry_but_forbidden_does_not(self):
        response = (self.body, 'application/pdf', 'https://publisher.test/source.pdf')
        error = HTTPError(response[2], 503, 'temporary', {}, None)
        with patch.object(sources, '_read_once', side_effect=[error, response]) as read, patch.object(sources.time, 'sleep'):
            self.assertEqual(sources._read(response[2]), response)
            self.assertEqual(read.call_count, 2)
        with patch.object(sources, '_read_once', side_effect=HTTPError(response[2], 403, 'forbidden', {}, None)) as read:
            with self.assertRaises(HTTPError): sources._read(response[2])
            self.assertEqual(read.call_count, 1)

    def test_progress_and_failure_do_not_drop_other_results(self):
        manual = dict(filename='manual.pdf', sha256=self.entry['sha256'])
        catalogue = ({'source.pdf': self.entry, 'manual.pdf': manual},
                     {'source.pdf': self.method, 'manual.pdf': dict(method='manual', instructions='Sign in at publisher.')})
        progress = []
        with patch.object(sources, 'load_catalogue', return_value=catalogue), patch.object(sources, '_read', side_effect=OSError('offline')):
            rows = sources.acquire(destination=self.root, progress=progress.append)
        self.assertEqual(len(progress), 2)
        self.assertEqual([r[1] for r in rows], ['failed', 'manual'])

    def test_job_rejects_invalid_token_prevents_duplicate_and_reloads(self):
        started = threading.Event(); release = threading.Event(); reloaded = threading.Event()
        def acquire(**kwargs):
            started.set(); release.wait(3)
            kwargs['progress'](('source.pdf', 'downloaded', 'publisher'))
        job = AcquisitionJob(reloaded.set)
        with patch.object(sources, 'acquire', side_effect=acquire) as download:
            self.assertFalse(job.start('invalid'))
            self.assertTrue(job.start(job.token))
            self.assertTrue(started.wait(2))
            self.assertTrue(job.start(job.token))
            self.assertEqual(download.call_count, 1)
            release.set(); self.assertTrue(reloaded.wait(2))
        self.assertEqual(job.snapshot()[1][0][1], 'downloaded')

    def test_source_page_escapes_status_and_instructions(self):
        job = AcquisitionJob(lambda: None)
        with self.catalogue(), patch.dict('os.environ', {'WACC_SOURCES': str(self.root)}):
            self.method['instructions'] = '<script>alert(1)</script>'
            page = render(job)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>alert', page)
        self.assertIn('method="post"', page)
        self.assertIn('name="token"', page)
        self.assertIn('1 are missing', page)


if __name__ == '__main__': unittest.main()
