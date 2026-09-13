"""Permission decisions control paths; changed bytes require another review."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wacc.packaging import approved_sources, check, excluded_but_present, gitignore, would_ship

ROOT = Path(__file__).resolve().parents[1]


class SourcePermissionTests(unittest.TestCase):
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

    def test_unreviewed_files_excluded_including_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            shipping = would_ship(str(root))
            self.assertIn(os.path.join('sources', 'files', 'approved.pdf'), shipping)
            self.assertFalse(any('unknown' in p for p in shipping))
            self.assertEqual(len(excluded_but_present(str(root))), 2)
            self.assertEqual(check(str(root)), [])

    def test_changed_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = self.fixture(root)
            (directory / 'approved.pdf').write_bytes(b'a different edition')
            self.assertIn('unreviewed source bytes', [v.rule for v in check(str(root))])

    def test_missing_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = self.fixture(root)
            (directory / 'approved.pdf').unlink()
            self.assertIn('missing approved source', [v.rule for v in check(str(root))])

    def test_no_manifest_does_not_approve_any_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sources' / 'files').mkdir(parents=True)
            (root / 'sources' / 'files' / 'unknown.json').write_text('{}')
            self.assertEqual(would_ship(str(root)), [])

    def test_manifest_cannot_escape_source_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            manifest = root / 'sources' / 'permissions.json'
            data = json.loads(manifest.read_text())
            data['files'][0]['filename'] = '../../outside.pdf'
            manifest.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                approved_sources(str(root))

    def test_real_archive_has_reviewed_bytes_and_no_excluded_file(self):
        self.assertEqual(check(str(ROOT)), [])
        manifest = json.loads((ROOT / 'sources' / 'permissions.json').read_text(encoding='utf-8'))
        approved = {e['filename'] for e in manifest['files'] if e['status'] == 'included'}
        actual = {p.name for p in (ROOT / 'sources' / 'files').iterdir()}
        self.assertEqual(actual, approved)
        self.assertTrue(any(e['status'] != 'included' for e in manifest['files']))

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
                         set(paths[-4:]))


if __name__ == '__main__':
    unittest.main()
