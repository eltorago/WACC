"""Checks the Control workspace data, filtering, exports and web pages."""
from pathlib import Path
import csv
import io
import sys
import unittest
from http.server import ThreadingHTTPServer
import threading
import urllib.request
from dataclasses import replace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc.serve import State, _handler
from wacc import control_workspace as workspace
from wacc import workspace_attack
from wacc.model import Corpus


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
    def test_all_sources_exist_and_anti_patterns_are_not_requirements(self):
        ids={c['id'] for c in workspace.CONTROLS}
        self.assertEqual(len(ids),84)
        self.assertEqual(len(workspace.TOPICS),30)
        for c in workspace.CONTROLS:
            self.assertGreaterEqual(len(c.get('test_steps', [])),3,c['id'])
            self.assertTrue(all(len(step)>=40 for step in c['test_steps']),c['id'])
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

    def test_september_2026_active_directory_guidance_is_loaded(self):
        framework=self.state.corpus.frameworks['asd-ad']
        self.assertEqual(framework.revision,'September 2026')
        shadow=[
            c for c in self.state.corpus.controls_for('asd-ad')
            if 'mitigating shadow credentials#' in c.identifier.lower()
        ]
        self.assertEqual(len(shadow),3)
        self.assertTrue(any('msDS-KeyCredentialLink' in c.text for c in shadow))
        dcsync=self.state.corpus.control('asd-ad:appendix a §mitigating dcsync#4')
        golden=self.state.corpus.control('asd-ad:appendix a §mitigating a golden ticket#1')
        self.assertIn('every 6 months',dcsync.text)
        self.assertIn('every 6 months',golden.text)
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
            self.assertIn('class="test-method"',page)
            for step in c['test_steps']:
                self.assertIn(step.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace("'",'&#x27;').replace('"','&quot;'),page)
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

    def test_topic_change_refreshes_and_framework_scope_follows_controls(self):
        page=self.get('/library')
        topic=page.index('id="topic"')
        controls=page.index('controls in scope')
        frameworks=page.index('<legend>Framework scope</legend>')
        self.assertIn('onchange="this.form.requestSubmit()"',page[topic:topic+250])
        self.assertLess(topic,controls)
        self.assertLess(controls,frameworks)

    def test_query_is_escaped_and_no_match_is_explicit(self):
        page=workspace.render(self.state.corpus,{'q':["<script>alert('nonexistent-control-xyzzy')</script>"]})
        self.assertNotIn("<script>alert('nonexistent-control-xyzzy')</script>",page)
        self.assertIn('No control selected',page)

    def test_every_control_has_a_specific_attack_assessment(self):
        self.assertEqual(set(workspace_attack.ASSESSMENTS), {c['id'] for c in workspace.CONTROLS})
        for uid, assessment in workspace_attack.ASSESSMENTS.items():
            self.assertTrue(assessment['connections'] or assessment.get('note'),uid)
            seen=set()
            for connection in assessment['connections']:
                key=(connection['technique'],connection['effect'])
                self.assertNotIn(key,seen,uid)
                seen.add(key)
                self.assertIn(connection['effect'],workspace_attack.EFFECTS)
                self.assertGreater(len(connection['how']),80,uid)
                self.assertEqual(workspace_attack.connection_status(connection,self.state.corpus),'',uid)
            page=self.get('/library?control='+uid)
            self.assertIn('id="attack"',page)
            self.assertNotIn('pending source verification',page)
        self.assertNotIn('attack-enterprise',workspace.FRAMEWORKS)

    def test_attack_relationships_show_their_actual_role_and_provenance(self):
        mfa=self.get('/library?control=MF-01')
        self.assertIn('https://attack.mitre.org/techniques/T1078/',mfa)
        self.assertIn('https://attack.mitre.org/techniques/T1110/004/',mfa)
        self.assertIn('https://attack.mitre.org/mitigations/M1032/',mfa)
        self.assertIn('Credential Stuffing',mfa)
        self.assertIn('Reduces likelihood',mfa)
        self.assertIn('local WACC assessments',mfa)
        self.assertIn('Supports detection',self.get('/library?control=SM-03'))
        self.assertIn('Limits impact / recovery',self.get('/library?control=BR-01'))
        self.assertIn('Enables other safeguards',self.get('/library?control=VM-01'))
        reporting=self.get('/library?control=IN-02')
        self.assertIn('No direct technique mapping',reporting)
        self.assertNotIn('https://attack.mitre.org/techniques/',reporting)

    def test_attack_search_and_export_respect_control_scope(self):
        selected=set(workspace.FRAMEWORKS)
        found=workspace.matching('T1110.004',selected,corpus=self.state.corpus)
        self.assertIn('MF-01',{c['id'] for c in found})
        self.assertNotIn('PW-01',{c['id'] for c in found})
        self.assertEqual(workspace.matching('T1110.999',selected,corpus=self.state.corpus),[])
        found=workspace.matching('Credential Stuffing',selected,corpus=self.state.corpus)
        self.assertIn('MF-01',{c['id'] for c in found})
        self.assertEqual(workspace.matching('T1110.004',set(),corpus=self.state.corpus),[])
        found=workspace.matching('T1110',selected,'Password security',self.state.corpus)
        self.assertTrue(found)
        self.assertTrue(all(c['topic']=='Password security' for c in found))
        params={'q':['Credential Stuffing'],'scope':['1'],'fw':['cis-controls']}
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv(params,self.state.corpus))))
        self.assertTrue(rows)
        self.assertTrue(all(r['Source UID'].startswith('cis-controls:') for r in rows))
        self.assertIn('MF-01',{r['Control'] for r in rows})

    def test_missing_or_changed_attack_source_is_not_reported_as_verified(self):
        empty=Corpus()
        page=workspace_attack.render('MF-01',empty)
        self.assertIn('source is not loaded',page)
        self.assertIn('pending source verification',page)
        self.assertNotIn('MITRE mitigation reference:',page)
        partial=Corpus(techniques=self.state.corpus.techniques,mitigations=self.state.corpus.mitigations)
        page=workspace_attack.render('MF-01',partial)
        self.assertIn('relationship needs review',page)
        self.assertNotIn('MITRE mitigation reference:',page)
        self.assertIn('has not yet been completed',workspace_attack.render('UNKNOWN',empty))
        changed=Corpus(techniques=self.state.corpus.techniques,
                       mitigations=self.state.corpus.mitigations,
                       mitigates=self.state.corpus.mitigates,
                       threat_sources={'attack-enterprise':replace(
                           self.state.corpus.threat_sources['attack-enterprise'],version='future-edition')})
        self.assertIn('edition differs',workspace_attack.render('MF-01',changed))


if __name__=='__main__':unittest.main()
