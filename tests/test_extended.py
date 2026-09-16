"""Regression checks for publisher imports, assessment modes and dated context."""
from pathlib import Path
import json
import re
import sys
import unittest
from urllib.parse import parse_qs, urlsplit
from html.parser import HTMLParser
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wacc.build import build
from wacc import control_workspace as workspace, workspace_technical as technical
from wacc.wa_audit_context import REPORTS
from wacc.framework_review import render as render_review
from wacc.io.xlsx import Workbook
from wacc.model import Corpus, Provenance, Licence
from wacc.loaders.extended import EssentialEightParser, scuba
from wacc.registry import FRAMEWORKS_BY_KEY

ROOT=Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self,text):
        super().__init__();self.links=[];self.feed(text)
    def handle_starttag(self,tag,attrs):
        if tag=='a': self.links.append(dict(attrs))


class ExtendedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.corpus,cls.report=build(False)

    def test_import_counts_and_source_text_preserved(self):
        expected={'scf':1534,'mcsb':86,'essential-eight':304,'scuba':109}
        for key,count in expected.items():
            records=self.corpus.controls_for(key)
            self.assertEqual(len(records),count,key)
            self.assertTrue(all(c.text.strip() for c in records))
            self.assertFalse(self.corpus.frameworks[key].warnings())
        book=Workbook(ROOT/'sources/files/secure-controls-framework-scf-2026-2.xlsx')
        _,rows=book.table('SCF 2026.2')
        for row in rows:
            if len(row)>3 and re.fullmatch(r'[A-Z]+-\d+(?:\.\d+)*',row[2]):
                from wacc.model import normalise_identifier
                self.assertEqual(self.corpus.control('scf:'+normalise_identifier(row[2])).text,row[3])
        self.assertIn('Suspicious Connector Activity',self.corpus.control('scuba:ms.securitysuite.4.1v1').text)
        self.assertNotIn('Rationale',self.corpus.control('scuba:ms.securitysuite.4.1v1').text)
        self.assertFalse(any(c.section_ref=='defender' for c in self.corpus.controls_for('scuba')))

    def test_only_exact_edition_scf_links_are_imported(self):
        links=[l for l in self.corpus.links if l.source_uid.startswith('scf:')]
        self.assertGreater(len(links),100)
        self.assertTrue(all(l.target_uid.startswith('csf:') for l in links))
        self.assertTrue(all(l.provenance==Provenance.PUBLISHED and not l.kind.carries_obligation for l in links))
        self.assertEqual(self.corpus.frameworks['scf'].licence,Licence.IMPORT_ONLY)
        self.assertFalse([l for l in self.corpus.links if l.source_uid.startswith('mcsb:') and l.target_uid.startswith('nist-800-53:')])

    def test_e8_maturity_tables_exclude_comparison_duplicates(self):
        parser=EssentialEightParser()
        parser.feed('<h2>Appendix A: Maturity Level One</h2><table><tr><td rowspan="2">Patch applications</td><td>First requirement</td></tr><tr><td>Second requirement</td></tr></table><h2>Appendix D: Comparison</h2><table><tr><td>Patch applications</td><td>Duplicate</td></tr></table>')
        self.assertEqual(parser.records,[('ML1','Patch applications','First requirement'),('ML1','Patch applications','Second requirement')])
        records=self.corpus.controls_for('essential-eight')
        self.assertEqual({c.publisher_tags['essential_eight_maturity'] for c in records},{'ML1','ML2','ML3'})
        self.assertEqual(len({c.section_ref for c in records}),24)

    def test_every_control_has_traceable_technical_checks(self):
        parents={c['id'] for c in workspace.CONTROLS}
        self.assertEqual(parents,{p for c in technical.CHECKS for p in c['parents']})
        self.assertEqual(len(technical.CHECKS),len({c['id'] for c in technical.CHECKS}))
        for c in technical.CHECKS:
            self.assertGreaterEqual(len(c['steps']),3,c['id'])
            self.assertGreaterEqual(len(c['artifacts']),2,c['id'])
            for key in ('prerequisites','expected','limitations'):
                self.assertGreater(len(c[key]),35,(c['id'],key))
            for key in c['sources']:
                self.assertTrue(technical.SOURCES[key][1].startswith('https://'))
            for uid in c['references']:
                self.assertIsNotNone(self.corpus.control(uid),uid)
        ad=[c for c in technical.CHECKS if c['id'].startswith('AD-CHECK-')]
        self.assertGreaterEqual(len(ad),14)
        self.assertTrue(all(c.get('vendor_context') for c in ad))

    def test_modes_preserve_filters_and_existing_grc(self):
        params={'control':['PA-03'],'assessment':['technical'],'q':['authentication'],'topic':['Privileged access'],'scope':['1'],'fw':['ism','scuba']}
        page=workspace.render(self.corpus,params)
        self.assertIn('TECH-CA',page)
        self.assertIn('GRC Focused',page)
        self.assertNotIn('<dt>Interview</dt>',page)
        toggle=[a for a in Links(page).links if a.get('aria-current')=='false'][0]
        query=parse_qs(urlsplit(toggle['href']).query)
        self.assertEqual(query['control'],['PA-03'])
        self.assertEqual(query['q'],['authentication'])
        self.assertEqual(set(query['fw']),{'ism','scuba'})
        self.assertEqual(query['topic'],['Privileged access'])
        self.assertIn('<dt>Interview</dt>',workspace.render(self.corpus,query))
        self.assertIn('name="assessment" value="technical"',page)
        self.assertIn('assessment=technical',page)
        self.assertNotIn('Evidence and result',page)

    def test_scoped_technical_references_and_missing_sources(self):
        html=technical.render('MF-01',self.corpus,{'ism'})
        self.assertNotIn('q=scuba',html)
        html=technical.render('MF-01',Corpus(),{'scuba'})
        self.assertIn('source not loaded',html)
        self.assertNotIn('q=scuba',html)
        self.assertEqual(workspace.matching('scuba:ms.aad.3.6v1',{'ism'}),[])
        self.assertIn('MF-01',{c['id'] for c in workspace.matching('scuba:ms.aad.3.6v1',{'scuba'})})

    def test_alphabetical_controls_and_topics(self):
        self.assertEqual(workspace.TOPICS,sorted(workspace.TOPICS,key=str.casefold))
        titles=[c['title'] for c in workspace.CONTROLS]
        self.assertEqual(titles,sorted(titles,key=str.casefold))
        self.assertNotEqual(workspace.TOPICS[0],'Privileged access')

    def test_audit_context_is_dated_and_navigable(self):
        self.assertEqual(len(REPORTS),13)
        parents={c['id'] for c in workspace.CONTROLS}
        for r in REPORTS:
            self.assertRegex(r['date'],r'^20\d\d-\d\d-\d\d$')
            self.assertTrue(set(r['controls'])<=parents)
            self.assertIn(r['key'],self.corpus.guidance)
        page=workspace.render(self.corpus,{'control':['DP-03']})
        self.assertIn('Read the OAG report',page)
        self.assertIn('Historical audit context',page)
        self.assertIn('Child Protection Case Management',page)

    def test_review_uses_column_counts_not_compliance_scores(self):
        review=json.loads((ROOT/'data/framework-review.json').read_text(encoding='utf-8'))
        self.assertEqual(len(review['inventory']),252)
        self.assertEqual(review['scf_controls'],1534)
        page=render_review(self.corpus)
        self.assertIn('not target requirements satisfied',page)
        self.assertIn('Licensed source needed',page)
        self.assertIn('AD-CHECK-01',page)

    def test_render_all_assessments_without_interpreting_commands_as_html(self):
        for c in workspace.CONTROLS:
            page=workspace.render(self.corpus,{'control':[c['id']],'assessment':['technical']})
            self.assertIn('Prerequisites and access',page,c['id'])
            self.assertIn('Expected result',page,c['id'])
        example=technical.CHECKS[0]
        old=example['command']
        try:
            example['command']='<script>test</script>'
            page=technical.render(example['parents'][0],self.corpus,set(workspace.FRAMEWORKS))
            self.assertIn('&lt;script&gt;test&lt;/script&gt;',page)
            self.assertNotIn('<script>test</script>',page)
        finally: example['command']=old


if __name__=='__main__': unittest.main()
