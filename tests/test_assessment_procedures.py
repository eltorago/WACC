"""Coverage, publisher provenance and offline command checks for workspace procedures."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wacc import control_workspace as workspace, workspace_technical as technical, workspace_grc
from wacc.build import build
from wacc.loaders.extended import StrategiesParser, StrategyDetailsParser, STRATEGY_TITLES
from wacc.model import Corpus
from wacc.serve import State


class AssessmentProceduresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.corpus,cls.report=build(False)

    def test_strategy_wording_and_all_37_detail_sections(self):
        parser=StrategiesParser(); parser.feed((ROOT/'sources/files/asd-strategies-2017.html').read_text(encoding='utf-8'))
        details=StrategyDetailsParser(); details.feed((ROOT/'sources/files/asd-strategies-details-2017.html').read_text(encoding='utf-8'))
        self.assertEqual(len(parser.records),37)
        self.assertEqual(set(details.records),set(STRATEGY_TITLES))
        self.assertEqual(len(self.corpus.controls_for('asd-strategies')),37)
        for i,row in enumerate(parser.records,1):
            control=self.corpus.control('asd-strategies:s%02d'%i)
            self.assertEqual(control.text,row[2])
            self.assertIn('February 2017',control.attributes['edition_note'])
            self.assertTrue(control.attributes['implementation_examples'])
        self.assertEqual(len({r[0] for r in parser.records}),5)

    def test_every_strategy_has_scoped_workspace_navigation(self):
        refs={m['uid'] for c in workspace.CONTROLS for m in c['mappings'] if m.get('uid','').startswith('asd-strategies:')}
        self.assertEqual(refs,{c.uid for c in self.corpus.controls_for('asd-strategies')})
        found=workspace.matching('asd-strategies:s01',{'asd-strategies'})
        self.assertIn('AP-01',{c['id'] for c in found})
        self.assertEqual(workspace.matching('asd-strategies:s01',{'cis-controls'}),[])
        page=workspace.render(self.corpus,{'control':['AP-01'],'scope':['1'],'fw':['asd-strategies']})
        self.assertIn('February 2017',page)
        self.assertIn('Publisher implementation guidance',page)

    def test_every_control_document_match_is_in_actual_published_examine_text(self):
        self.assertEqual(set(workspace_grc.EVIDENCE),{c['id'] for c in workspace.CONTROLS})
        for cid,evidence in workspace_grc.EVIDENCE.items():
            statements=[s for s in self.corpus.statements_for(evidence['source_uid']) if s.is_published and s.published_ref==evidence['published_ref']]
            self.assertEqual(len(statements),1,cid)
            self.assertTrue(statements[0].text.startswith('Examine:'),cid)
            for document in evidence['documents']:
                self.assertIn(document.casefold(),statements[0].text.casefold(),(cid,document))
            self.assertGreater(len(evidence['application']),100,cid)

    def test_supplier_risk_register_is_explicit_and_scoped(self):
        page=workspace.render(self.corpus,{'control':['SC-02']})
        self.assertIn('risk register documentation',page)
        self.assertIn('NIST SP 800-53A Rev 5.2.0',page)
        self.assertIn('residual risk',page)
        self.assertEqual(workspace_grc.render('SC-02',self.corpus,{'ism'}),'')
        missing=workspace_grc.render('SC-02',Corpus(),{'nist-800-53'})
        self.assertIn('needs revalidation',missing)
        self.assertNotIn('Document names checked against',missing)

    def test_58_checks_have_prerequisites_sources_steps_and_honest_validation(self):
        data=technical.PROCEDURES
        self.assertEqual(set(data['checks']),{c['id'] for c in technical.CHECKS})
        self.assertEqual(len(data['checks']),58)
        for cid,procedure in data['checks'].items():
            self.assertGreaterEqual(len(procedure['run_steps']),4,cid)
            self.assertTrue(procedure['command'].startswith("$ErrorActionPreference = 'Stop'"),cid)
            for profile in procedure['profile'].split('+'): self.assertIn(profile,data['profiles'])
            for key in procedure['sources']:
                self.assertTrue(technical.COMMAND_SOURCES[key]['url'].startswith('https://learn.microsoft.com/'),(cid,key))
            self.assertEqual(procedure['validation']['environment_execution'],'Not performed in an AD/M365/Azure test environment',cid)
            self.assertEqual(procedure['validation']['command_sha256'],hashlib.sha256(procedure['command'].encode()).hexdigest(),cid)
            self.assertIn('syntax',procedure['validation']['summary'].lower())
            self.assertNotIn('fully validated',procedure['validation']['summary'].lower())
        reviewed=json.loads((ROOT/'data/assessment-source-review.json').read_text(encoding='utf-8'))['sources']
        self.assertEqual(set(reviewed),set(technical.COMMAND_SOURCES))
        self.assertTrue(all(s['status']=='retrieved' for s in reviewed.values()))

    def test_app_control_distinguishes_static_audit_and_runtime(self):
        procedure=technical.PROCEDURES['checks']['TECH-APP-CONTROL']
        text=json.dumps(procedure)
        for term in ('CiTool','Get-AppLockerPolicy','Test-AppLockerPolicy','CSP','3076','3077','3099','8003','8004','8029','Audit Mode','Constrained'):
            self.assertIn(term.lower(),text.lower())
        self.assertIn('does not execute',text)
        page=workspace.render(self.corpus,{'control':['AP-01'],'assessment':['technical']})
        self.assertIn('Copy commands',page)
        self.assertIn('Run this check',page)
        self.assertIn('Validation:',page)

    def test_powershell_parsing_and_offline_fixtures(self):
        engines=[p for p in (shutil.which('powershell'),shutil.which('pwsh')) if p]
        if not engines: self.skipTest('PowerShell not installed; do not claim command execution on this host')
        for engine in engines:
            args=[engine,'-NoProfile']
            if os.name=='nt': args+=['-ExecutionPolicy','RemoteSigned']
            parser=subprocess.run(args+['-File',str(ROOT/'tools/validate_assessment_commands.ps1')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
            self.assertEqual(parser.returncode,0,parser.stderr)
            parsed=json.loads(parser.stdout.lstrip('\ufeff'))
            self.assertEqual(len(parsed),58)
            self.assertTrue(all(not row['errors'] for row in parsed))
            fixtures=subprocess.run(args+['-File',str(ROOT/'tests/test_assessment_commands.ps1')],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=45)
            self.assertEqual(fixtures.returncode,0,fixtures.stdout+fixtures.stderr)
            self.assertIn('OFFLINE FIXTURES: 16 passed',fixtures.stdout)


if __name__=='__main__': unittest.main()
