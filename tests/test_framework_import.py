"""Execute the README's manual OSCAL preview workflow and reject broken imports."""
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.validate_framework import validate


class FrameworkImportTests(unittest.TestCase):
    def setUp(self):
        self.folder=ROOT/('.wacc-test-'+uuid.uuid4().hex)
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree,self.folder)
        self.data=json.loads((ROOT/'tests/fixtures/onboarding-catalog.json').read_text(encoding='utf-8'))

    def preview(self,expected=1):
        p=self.folder/'catalog.json'
        p.write_text(json.dumps(self.data),encoding='utf-8')
        return validate(p,'example-fw',expected,'Example publisher')

    def test_readme_example_loads_text_and_published_assessment(self):
        result=self.preview()
        self.assertEqual(result['problems'],[])
        self.assertEqual(result['uids'],['example-fw:ex-1'])
        self.assertEqual(result['counts']['assessment_methods'],1)

    def test_duplicate_normalised_ids_rejected(self):
        duplicate=dict(self.data['catalog']['controls'][0]);duplicate['id']='EX-01'
        self.data['catalog']['controls'].append(duplicate)
        self.assertTrue(any('duplicate' in p for p in self.preview()['problems']))

    def test_empty_missing_text_and_wrong_count_rejected(self):
        self.assertTrue(self.preview(2)['problems'])
        self.data['catalog']['controls'][0]['parts']=[]
        self.assertTrue(any('Missing statement' in p for p in self.preview()['problems']))
        self.data['catalog']['controls']=[]
        self.assertTrue(any('No controls' in p for p in self.preview()['problems']))


if __name__=='__main__': unittest.main()
