"""Offline update tests: publisher selection, isolation, activation and recovery."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
from test_policy_review import temporary
from wacc.policy import updates, corpus, documents
from wacc.policy.contracts import PolicyError


def fixture(version='2026.1.1'):
    # Explicit synthetic test catalogue, never a shipped framework.
    return json.dumps({'catalog':{'uuid':'00000000-0000-0000-0000-000000000001',
        'metadata':{'title':'Information Security Manual — synthetic parser fixture','version':version},
        'controls':[{'id':'ism-9999','title':'Synthetic test control','parts':[{'id':'ism-9999_smt','name':'statement','prose':'Synthetic policy evidence is retained.'}]}]}}).encode()


class FrameworkUpdateTests(unittest.TestCase):
    def test_download_rejects_nonpublisher_before_network_access(self):
        with patch('wacc.policy.updates.build_opener',side_effect=AssertionError('Network must not be called')):
            for url in ('http://www.wa.gov.au/file.pdf','https://evil.example/file.pdf','https://www.wa.gov.au@evil.example/file.pdf','https://www.wa.gov.au:9443/file.pdf'):
                with self.subTest(url=url), self.assertRaises((PolicyError,ValueError)):
                    updates.download(url,'wa-csp')
            with self.assertRaises(PolicyError):
                updates.download('https://raw.githubusercontent.com/Other/repo/main/catalog.json','ism')

    def test_discovery_chooses_core_over_toolkit_and_older_edition(self):
        body=b'<a href="/core-v1.xlsx">AESCSF v1 Core</a><a href="/core-v2.xlsx">AESCSF v2 Core</a><a href="/toolkit.xlsx">AESCSF v3 Toolkit</a>'
        with patch('wacc.policy.updates.download',return_value=(body,updates.PAGES['aescsf'])):
            self.assertEqual(updates.discover('aescsf'),'https://www.aemo.com.au/core-v2.xlsx')
        body=b'<a href="/overview.pdf">WA Government Cyber Security Policy overview 2024</a><a href="/policy.pdf">WA Government Cyber Security Policy 2024</a>'
        with patch('wacc.policy.updates.download',return_value=(body,updates.PAGES['wa-csp'])):
            self.assertEqual(updates.discover('wa-csp'),'https://www.wa.gov.au/policy.pdf')

    def test_local_update_activates_without_wa_baseline_and_preserves_versions(self):
        with temporary() as root, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(root/'cache'),'WACC_LIBRARY':str(root/'empty-library')}):
            path=root/'synthetic.json';path.write_bytes(fixture())
            result=updates.update(['ism'],path)
            self.assertEqual(result[0]['status'],'Updated',result)
            first=updates.current('ism')
            loaded=corpus.load('ism')
            self.assertEqual(len(loaded['requirements']),1)
            self.assertTrue(all(a['rule'] is None for a in loaded['requirements'][0]['obligations']))
            self.assertEqual(updates.update(['ism'],path)[0]['status'],'Unchanged')
            path.write_bytes(fixture('2026.2.1'))
            self.assertEqual(updates.update(['ism'],path)[0]['status'],'Updated')
            self.assertNotEqual(first['framework']['sourceHash'],updates.current('ism')['framework']['sourceHash'])
            self.assertEqual(len(list((root/'cache/versions/ism').iterdir())),2)

    def test_failed_update_and_failed_activation_keep_previous_version(self):
        with temporary() as root, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(root/'cache')}):
            path=root/'synthetic.json';path.write_bytes(fixture());updates.update(['ism'],path)
            first=deepcopy(updates.current('ism'))
            path.write_text('not JSON')
            self.assertEqual(updates.update(['ism'],path)[0]['status'],'Failed')
            self.assertEqual(updates.current('ism'),first)
            path.write_bytes(fixture('2026.2.1'))
            write=updates.write_output
            def fail_index(path,*args,**kwargs):
                if Path(path).name=='current.json':raise OSError('simulated disk failure')
                return write(path,*args,**kwargs)
            with patch('wacc.policy.updates.write_output',side_effect=fail_index):
                self.assertEqual(updates.update(['ism'],path)[0]['status'],'Failed')
            self.assertEqual(updates.current('ism'),first)

    def test_modified_cached_source_is_rejected(self):
        with temporary() as root, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(root/'cache')}):
            path=root/'synthetic.json';path.write_bytes(fixture());updates.update(['ism'],path)
            cached=next((root/'cache/versions').rglob('ISM_catalog.json'));cached.write_bytes(b'changed')
            with self.assertRaises(PolicyError):updates.current('ism')

    def test_worker_does_not_import_rules_supplied_by_publisher(self):
        with temporary() as root:
            data=json.loads(fixture());data['catalog']['controls'][0]['rule']={'shell':'forbidden'}
            path=root/'synthetic.json';path.write_text(json.dumps(data))
            value=documents.extract_worker(path,framework='ism')
            self.assertNotIn('rule',value['requirements'][0])
            self.assertNotIn('obligations',value['requirements'][0])

    def test_update_lock_blocks_concurrent_writer(self):
        with temporary() as root, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(root)}):
            with updates.update_lock(root):
                with self.assertRaises(PolicyError):updates.update(['ism'])

    def test_corrupt_cache_has_a_controlled_error_and_does_not_break_inventory(self):
        with temporary() as root, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(root)}):
            (root/'current.json').write_text('not JSON')
            with self.assertRaises(PolicyError):updates.current('ism')
            inventory=corpus.installed()
            self.assertTrue(inventory['baselineError'])


if __name__=='__main__':unittest.main()
