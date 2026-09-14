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
        self.assertEqual(len(ids),83)
        self.assertEqual(len(workspace.TOPICS),30)
        for c in workspace.CONTROLS:
            self.assertTrue(set(c['related'])<=ids)
            for other in c['related']:
                self.assertIn(c['id'], next(x['related'] for x in workspace.CONTROLS if x['id']==other))
            for m in c['mappings']:
                if 'uid' in m:
                    self.assertIsNotNone(self.state.corpus.control(m['uid']),m['uid'])
                else:
                    self.assertIn(m['guidance'], self.state.corpus.guidance)
                    self.assertTrue(m['excerpt'])
                self.assertEqual(m['provenance'],'Locally reviewed mapping')
                if not c['id'].startswith(('PA-','BR-','SM-','VM-')):
                    self.assertIn(m['relationship'],('Directly addresses','Partially addresses','Related only'))
                if '-ap' in m.get('uid',''):
                    self.assertEqual(m['relationship'],'Related only')
    def test_scope_and_export_exclude_deselected_frameworks(self):
        params={'scope':['1'],'fw':['cis-controls']}
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv(params))))
        expected={c['id'] for c in workspace.CONTROLS if any(m.get('uid','').startswith('cis-controls:') for m in c['mappings'])}
        self.assertEqual({r['Control'] for r in rows},expected)
        self.assertTrue(all(r['Source UID'].startswith('cis-controls:') for r in rows))
        self.assertEqual(workspace.matching('',workspace.scope({'scope':['1']})),[])
        self.assertEqual(len(list(csv.reader(io.StringIO(workspace.export_csv({'scope':['1']}))))),1)
        guidance=list(csv.DictReader(io.StringIO(workspace.export_csv({'scope':['1'],'fw':['guidance']}))))
        self.assertTrue(guidance)
        self.assertTrue(all(r['Source UID'].startswith('guidance:') for r in guidance))
    def test_identifier_search_finds_canonical_control(self):
        found=workspace.matching('ISM-1507',set(workspace.FRAMEWORKS))
        self.assertEqual([c['id'] for c in found],['PA-01'])
        self.assertEqual(workspace.matching('ISM-1507', {'cis-controls'}), [])

    def test_new_topics_cover_the_requested_source_sets(self):
        required={
            'Multi-factor authentication':{'ism','nist-800-53','nist-800-63','cis-controls','aescsf','pspf','oag-wa','asd-ad'},
            'Application control':{'ism','pspf','wa-csp','cis-controls','asd-ad','oag-wa','nist-800-53'},
            'Cryptographic keys and algorithms':{'nist-800-57pt1','nist-800-131a','ism','nist-800-63','nist-800-53'},
            'Media sanitisation and disposal':{'ism','nist-800-53','nist-800-88','wa-csp','pspf'},
            'Incident notification timeframes':{'soci-act','wa-csp','wa-circular'},
            'Supply chain and third-party risk':{'csf','ism','nist-800-53','aescsf','wa-csp','cirmp-rules','pspf','oag-wa','cis-controls'},
            'Physical security':{'pspf','ism','nist-800-53','oag-wa','aescsf'},
            'Asset inventory and configuration/change management':{'cis-controls','nist-800-53','aescsf','oag-wa'},
            'Network architecture and segmentation':{'ism','nist-800-53','cis-controls','aescsf','guidance'},
            'Security awareness and workforce training':{'cis-controls','nist-800-53','aescsf','oag-wa'},
            'Operational technology security':{'oag-wa','aescsf','c2m2','guidance'},
            'Identity and access management':{'wa-csp','oag-wa','nist-800-53','cis-controls','c2m2','csf'},
            'Incident response and management':{'wa-csp','nist-800-53','cis-controls','c2m2','pspf','csf'},
            'Data protection':{'cis-controls','nist-800-53','ztmm','ism','c2m2','aescsf'},
            'Secure software development':{'cis-controls','nist-800-53','csf','c2m2','ism','ztmm'},
            'Business continuity and resilience':{'oag-wa','nist-800-53','c2m2','pspf','wa-csp'},
            'Active Directory security':{'ism','asd-ad','nist-800-53','cis-controls','aescsf','c2m2','oag-wa'},
            'Cybersecurity risk assessment':{'ism','nist-800-53','csf','aescsf','c2m2','wa-csp'},
            'Security testing and assurance':{'ism','nist-800-53','cis-controls','aescsf','c2m2','ztmm'},
            'Mobile and wireless security':{'ism','nist-800-53','cis-controls','aescsf','c2m2'},
            'Privacy and personal information':{'ism','nist-800-53','aescsf','pspf'},
            'Password security':{'ism','nist-800-53','nist-800-63','cis-controls','aescsf','c2m2','wa-csp','asd-ad','oag-wa'},
        }
        for topic, expected in required.items():
            actual={workspace.mapping_source_key(m) for c in workspace.CONTROLS if c['topic']==topic for m in c['mappings']}
            self.assertTrue(expected<=actual,(topic,expected-actual))
    def test_home_and_each_control_render_without_record_entry(self):
        self.assertIn('Control workspace',self.get('/'))
        for c in workspace.CONTROLS:
            page=self.get('/library?control='+c['id'])
            self.assertIn(c['title'],page)
            self.assertNotIn('Evidence and result',page)
            self.assertNotIn('localStorage',page)
            self.assertNotIn('Not assessed',page)
            self.assertIn('Open source control',page)
            self.assertNotIn('Download assessment',page)
            self.assertIn('Assess this control',page)
        page=self.get('/library?scope=1&fw=cis-controls&control=PA-01')
        self.assertNotIn('q=ism%3Aism-1507',page)
        self.assertIn('q=cis-controls%3A6.1',page)
        guidance=self.get('/library?scope=1&fw=guidance&control=OT-02')
        self.assertIn('UK NCSC',guidance)
        self.assertIn('Guidance context',guidance)
        self.assertNotIn('Source text is not loaded',guidance)
    def test_topic_filter_applies_to_list_and_export(self):
        selected=set(workspace.FRAMEWORKS)
        controls=workspace.matching('', selected, 'Backup and recovery')
        self.assertEqual({c['id'] for c in controls},{'BR-01','BR-02','BR-03'})
        self.assertEqual(workspace.matching('privileged access', selected, 'Backup and recovery'),[])
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv({'topic':['Backup and recovery']}))))
        self.assertTrue(all(r['Control'].startswith('BR-') for r in rows))
        page=self.get('/library?topic=Backup+and+recovery&control=BR-02')
        self.assertIn('BR-02 · Backup and recovery',page)
        self.assertNotIn('id="choose-record"',page)
        self.assertNotIn('data-record-id=',page)

    def test_query_is_escaped_and_no_match_is_explicit(self):
        page=workspace.render(self.state.corpus,{'q':['<script>alert(1)</script>']})
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('No control selected',page)


if __name__=='__main__':unittest.main()
