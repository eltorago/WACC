"""Regression checks for defects found while reviewing the delivered patches."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import patch_status
from tools.textjoin import join_wrapped, mend_hyphen


class PatchIntegrationTests(unittest.TestCase):
    def test_wrapped_suspended_hyphen_keeps_its_space(self):
        self.assertEqual(join_wrapped(['security-', 'and privacy-related']),
                         'security- and privacy-related')
        self.assertEqual(join_wrapped(['hardware-', 'or software-based']),
                         'hardware- or software-based')
        self.assertEqual(join_wrapped(['enterprise-', 'wide risk']), 'enterprise-wide risk')
        self.assertEqual(mend_hyphen('security-\nand\nprivacy'), 'security- and\nprivacy')

    def test_unknown_patch_commit_does_not_overwrite_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.patch').write_text('From abc123 Mon Sep 17\nSubject: [PATCH] Test\n')
            manifest = root / 'MANIFEST.json'
            manifest.write_text('original evidence')
            with patch.object(patch_status, 'PATCHES', directory), \
                 patch.object(patch_status, 'MANIFEST', str(manifest)), \
                 patch.object(patch_status, 'APPLIED', str(root / 'APPLIED.json')), \
                 patch.object(patch_status, '_git', side_effect=subprocess.CalledProcessError(128, 'git')), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(patch_status.record(), 2)
            self.assertEqual(manifest.read_text(), 'original evidence')

    def test_empty_manifest_is_not_proof_of_applied_patches(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'MANIFEST.json'
            for entries in ([], [{'patch': 'test.patch', 'files_after': {}, 'files_before': {}}]):
                manifest.write_text(json.dumps({'patches': entries}))
                with patch.object(patch_status, 'MANIFEST', str(manifest)), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(patch_status.check(directory), 2)


if __name__ == '__main__':
    unittest.main()
