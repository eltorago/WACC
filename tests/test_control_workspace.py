"""Pilot scope, mapping integrity and HTTP navigation checks."""
from pathlib import Path
import csv
import io
import sys
import unittest
from http.server import ThreadingHTTPServer
import threading
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc.serve import State, _handler
from wacc import control_workspace as workspace


class ControlWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=State()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),_handler(cls.state))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base='http://127.0.0.1:%d'%cls.server.server_port
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def get(self,path):
        with urllib.request.urlopen(self.base+path,timeout=15) as response:
            self.assertEqual(response.status,200)
            return response.read().decode('utf-8')
    def test_all_pilot_sources_exist_and_anti_patterns_are_not_requirements(self):
        ids={c['id'] for c in workspace.CONTROLS}
        self.assertEqual(len(ids),13)
        for c in workspace.CONTROLS:
            self.assertTrue(set(c['related'])<=ids)
            for other in c['related']:
                self.assertIn(c['id'], next(x['related'] for x in workspace.CONTROLS if x['id']==other))
            for m in c['mappings']:
                self.assertIsNotNone(self.state.corpus.control(m['uid']),m['uid'])
                self.assertEqual(m['provenance'],'Locally reviewed mapping')
                if '-ap' in m['uid']:
                    self.assertEqual(m['relationship'],'Related only')
    def test_scope_and_export_exclude_deselected_frameworks(self):
        params={'scope':['1'],'fw':['cis-controls']}
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv(params))))
        self.assertEqual(len({r['Control'] for r in rows}),13)
        self.assertTrue(all(r['Source UID'].startswith('cis-controls:') for r in rows))
        self.assertEqual(workspace.matching('',workspace.scope({'scope':['1']})),[])
        self.assertEqual(len(list(csv.reader(io.StringIO(workspace.export_csv({'scope':['1']}))))),1)
    def test_identifier_search_finds_canonical_control(self):
        found=workspace.matching('ISM-1507',set(workspace.FRAMEWORKS))
        self.assertEqual([c['id'] for c in found],['PA-01'])
        self.assertEqual(workspace.matching('ISM-1507', {'cis-controls'}), [])
    def test_home_and_each_control_render_with_records_and_source_navigation(self):
        self.assertIn('Control workspace',self.get('/'))
        for c in workspace.CONTROLS:
            page=self.get('/library?control='+c['id'])
            self.assertIn(c['title'],page)
            self.assertIn('id="assessment-record"',page)
            self.assertIn('Open source control',page)
            self.assertIn('Download assessment',page)
        page=self.get('/library?scope=1&fw=cis-controls&control=PA-01')
        self.assertNotIn('q=ism%3Aism-1507',page)
        self.assertIn('q=cis-controls%3A6.1',page)
    def test_topic_filter_applies_to_list_and_export(self):
        selected=set(workspace.FRAMEWORKS)
        controls=workspace.matching('', selected, 'Backup and recovery')
        self.assertEqual({c['id'] for c in controls},{'BR-01','BR-02','BR-03'})
        self.assertEqual(workspace.matching('privileged access', selected, 'Backup and recovery'),[])
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv({'topic':['Backup and recovery']}))))
        self.assertTrue(all(r['Control'].startswith('BR-') for r in rows))
        page=self.get('/library?topic=Backup+and+recovery&control=BR-02')
        self.assertIn('BR-02 · Backup and recovery',page)
        self.assertIn('id="choose-record"',page)
        self.assertIn('data-record-id="BR-02"',page)

    def test_restore_validator_rejects_wrong_control_and_malformed_records(self):
        import shutil
        import subprocess
        if not shutil.which('node'):
            self.skipTest('Node is needed only for the browser record validator tests')
        js=workspace.SCRIPT.split('(function(){',1)[0]+r"""
const assert=require('node:assert/strict');
const a={owner:'Example',date:'2026-09-14',scope:'Example',applicability:'Applicable',result:'Partially effective',evidence:'Example',findings:'Example',actions:'Example'};
const data={version:1,control:{id:'BR-01'},assessment:a};
assert.deepEqual(validateRecord(data,'BR-01'),a);
assert.throws(()=>validateRecord(data,'PA-01'));
assert.throws(()=>validateRecord({...data,version:2},'BR-01'));
assert.throws(()=>validateRecord({...data,assessment:{...a,result:'Compliant'}},'BR-01'));
assert.throws(()=>validateRecord({...data,assessment:{...a,date:'2026-02-31'}},'BR-01'));
assert.throws(()=>validateRecord({...data,assessment:{...a,owner:{html:'bad'}}},'BR-01'));
assert.throws(()=>validateRecord({...data,assessment:{...a,unexpected:'bad'}},'BR-01'));
assert.deepEqual(data.assessment,a);
"""
        result=subprocess.run(['node'],input=js,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_query_is_escaped_and_no_match_is_explicit(self):
        page=workspace.render(self.state.corpus,{'q':['<script>alert(1)</script>']})
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('No control selected',page)


if __name__=='__main__':unittest.main()
