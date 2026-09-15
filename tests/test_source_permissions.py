"""Publisher files stay local; acquisition and changed bytes remain controlled."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wacc.packaging import approved_sources, check, excluded_but_present, gitignore, would_ship
from wacc.sources import acquire_one, load_catalogue

ROOT = Path(__file__).resolve().parents[1]


class SourcePermissionTests(unittest.TestCase):
    def setUp(self):
        self.test_root = ROOT / (".wacc-permission-test-" + uuid.uuid4().hex)
        self.test_root.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_root, ignore_errors=True)

    def fixture(self, root):
        directory = root / 'sources' / 'files'
        directory.mkdir(parents=True)
        (directory / 'approved.pdf').write_bytes(b'reviewed publisher file')
        (directory / 'unknown.pdf').write_bytes(b'not reviewed')
        (directory / 'unknown.json').write_bytes(b'{}')
        entry = {'filename': 'approved.pdf', 'status': 'included',
                 'sha256': hashlib.sha256(b'reviewed publisher file').hexdigest()}
        (root / 'sources' / 'permissions.json').write_text(
            json.dumps({'files': [entry]}), encoding='utf-8')
        return directory

    def test_every_source_file_is_excluded_including_reviewed_bytes(self):
        root = self.test_root
        self.fixture(root)
        shipping = would_ship(str(root))
        self.assertFalse(any(p.startswith(os.path.join('sources', 'files')) for p in shipping))
        self.assertEqual(len(excluded_but_present(str(root))), 3)
        self.assertEqual(check(str(root)), [])

    def test_changed_source_is_rejected(self):
        root = self.test_root
        directory = self.fixture(root)
        (directory / 'approved.pdf').write_bytes(b'a different edition')
        self.assertIn('unreviewed source bytes', [v.rule for v in check(str(root))])

    def test_missing_source_is_valid_for_a_clean_checkout(self):
        root = self.test_root
        directory = self.fixture(root)
        (directory / 'approved.pdf').unlink()
        self.assertEqual(check(str(root)), [])

    def test_no_manifest_does_not_approve_any_source(self):
        root = self.test_root
        (root / 'sources' / 'files').mkdir(parents=True)
        (root / 'sources' / 'files' / 'unknown.json').write_text('{}')
        self.assertEqual(would_ship(str(root)), [])

    def test_manifest_cannot_escape_source_directory(self):
        root = self.test_root
        self.fixture(root)
        manifest = root / 'sources' / 'permissions.json'
        data = json.loads(manifest.read_text())
        data['files'][0]['filename'] = '../../outside.pdf'
        manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            approved_sources(str(root))

    def test_real_local_cache_has_only_reviewed_bytes_when_present(self):
        self.assertEqual(check(str(ROOT)), [])
        manifest = json.loads((ROOT / 'sources' / 'permissions.json').read_text(encoding='utf-8'))
        reviewed = {e['filename'] for e in manifest['files']}
        actual = {p.name for p in (ROOT / 'sources' / 'files').iterdir()}
        self.assertTrue(actual)
        self.assertTrue(actual <= reviewed)
        self.assertTrue(any(e['status'] != 'included' for e in manifest['files']))
        self.assertFalse(any(p.startswith(os.path.join('sources','files')) for p in would_ship(str(ROOT))))

    def test_every_permission_entry_has_an_acquisition_method(self):
        permissions, acquisition = load_catalogue()
        self.assertEqual(set(permissions), set(acquisition))
        self.assertTrue(all(item['method'] in ('automatic','manual') for item in acquisition.values()))
        self.assertTrue(all(item.get('urls') for item in acquisition.values()
                            if item['method'] == 'automatic'))
        self.assertTrue(all(item.get('instructions') for item in acquisition.values()
                            if item['method'] == 'manual'))

    def test_acquisition_accepts_only_the_reviewed_hash(self):
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        import threading
        from zipfile import ZipFile

        remote = self.test_root / 'remote'
        remote.mkdir()
        body = b'reviewed publisher file'
        (remote / 'source.pdf').write_bytes(body)
        with ZipFile(remote / 'sources.zip', 'w') as archive:
            archive.writestr('release/approved.pdf', body)
        class QuietHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(remote), **kwargs)

            def log_message(self, format, *args):
                pass

        handler = QuietHandler
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            entry = {'filename':'approved.pdf','sha256':hashlib.sha256(body).hexdigest()}
            method = {'method':'automatic','urls':[
                'http://127.0.0.1:%d/source.pdf' % server.server_port]}
            destination = self.test_root / 'downloaded'
            state, _ = acquire_one(entry, method, destination)
            self.assertEqual(state, 'downloaded')
            self.assertEqual((destination / 'approved.pdf').read_bytes(), body)
            entry['sha256'] = hashlib.sha256(b'another edition').hexdigest()
            state, _ = acquire_one(entry, method, destination, force=True)
            self.assertEqual(state, 'failed')
            self.assertEqual((destination / 'approved.pdf').read_bytes(), body)
            entry['sha256'] = hashlib.sha256(body).hexdigest()
            archive_method = {'method':'automatic','urls':[
                'http://127.0.0.1:%d/sources.zip' % server.server_port],
                'archive_member':'approved.pdf'}
            archive_destination = self.test_root / 'from-archive'
            state, _ = acquire_one(entry, archive_method, archive_destination)
            self.assertEqual(state, 'downloaded')
            self.assertEqual((archive_destination / 'approved.pdf').read_bytes(), body)
        finally:
            server.shutdown()
            server.server_close()

    def test_generated_ignore_rules_match_git_and_keep_unknown_files_out(self):
        self.assertEqual((ROOT / '.gitignore').read_text(encoding='utf-8'), gitignore())
        paths = [p.replace(os.sep, '/') for p in approved_sources(str(ROOT))]
        paths += ['sources/files/unknown.pdf', 'sources/files/unknown.json',
                  'data/raw/unreviewed.pdf', 'somewhere/approved.pdf']
        result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin', '-z'],
                                input=('\0'.join(paths)+'\0').encode('utf-8'),
                                capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.decode('utf-8').rstrip('\0').split('\0')),
                         set(paths))


if __name__ == '__main__':
    unittest.main()
