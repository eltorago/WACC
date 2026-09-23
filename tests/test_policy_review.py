"""End-to-end policy review, adversarial extraction and immutable assessment tests."""
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc.policy import corpus, documents, service, store, reports, rules
from wacc.policy.contracts import PolicyError, fingerprint, canonical_payload, validate_run


@contextmanager
def temporary():
    path = ROOT / 'data/local' / ('policy-test-' + uuid.uuid4().hex)
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        assert path.resolve().parent == (ROOT / 'data/local').resolve()
        shutil.rmtree(path)


def training(run):
    return next(r for r in run['requirements'] if r['id'] == 'wa-csp:3.2a')


class PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (ROOT/'data/corpus/wa-csp.json').exists():
            raise unittest.SkipTest('Prepare the locally permitted WA policy extract to run real-corpus policy checks.')
        cls.baseline = service.analyse([ROOT/'examples/policy-review/positive.md'], scope='Synthetic single policy', approval='approved', retention='extracted')

    def analyse_text(self, text, **kwargs):
        with temporary() as directory:
            path = directory/'policy.txt'
            path.write_text(text, encoding='utf-8')
            return service.analyse([path], scope='Synthetic test scope', approval=kwargs.pop('approval', 'approved'), **kwargs)

    def test_positive_partial_negative_and_ambiguous(self):
        for name, expected in [('positive','FullCandidate'),('partial','PartialCandidate'),('negative','NoEvidenceFound'),('ambiguous','Ambiguous')]:
            with self.subTest(name=name):
                r=service.analyse([ROOT/'examples/policy-review'/f'{name}.md'],scope='Synthetic test',approval='approved')
                self.assertEqual(training(r)['automatedFinding'],expected)

    def test_exact_source_spans_and_rule_trace(self):
        r=self.analyse_text('All personnel must complete cyber\nsecurity awareness training annually.')
        self.assertEqual(training(r)['automatedFinding'],'FullCandidate')
        for e in training(r)['evidence']:
            self.assertTrue(e['matchedSpans'])
            self.assertTrue(e['checks'])
            self.assertEqual(e['documentHash'],r['documents'][0]['sha256'])
            self.assertIn('cyber\nsecurity awareness training',[e['excerpt'][s['start']:s['end']].replace('\r\n','\n') for s in e['matchedSpans']])

    def test_unrelated_annual_review_is_not_joined(self):
        for text in ['All personnel must complete security awareness training. The help desk reviews tickets annually.',
                     'All personnel must complete security awareness training regularly and review tickets annually.']:
            self.assertEqual(training(self.analyse_text(text))['automatedFinding'],'PartialCandidate')

    def test_cooccurrence_is_not_a_training_commitment(self):
        r=self.analyse_text('All personnel must complete a form before considering security awareness training annually.')
        self.assertNotEqual(training(r)['automatedFinding'],'FullCandidate')

    def test_frequency_anchor_is_not_invented(self):
        r=self.analyse_text('All personnel must complete security awareness training within 12 months of appointment.')
        self.assertEqual(training(r)['automatedFinding'],'PartialCandidate')

    def test_background_heading_does_not_establish_adoption(self):
        r=self.analyse_text('# Background\n\nAll personnel must complete security awareness training annually.')
        self.assertEqual(training(r)['automatedFinding'],'Ambiguous')

    def test_negation_and_quoted_context(self):
        for text in ['All personnel are not required to complete security awareness training annually.',
                     '"All personnel must complete security awareness training annually."']:
            self.assertEqual(training(self.analyse_text(text))['automatedFinding'],'Ambiguous')

    def test_conflicts_preserve_both_passages(self):
        r=self.analyse_text('All personnel must complete security awareness training annually.\n\nSecurity awareness training is not required.')
        self.assertEqual(training(r)['automatedFinding'],'Ambiguous')
        self.assertIn('Conflict',training(r)['flags'])
        self.assertTrue(any(e['state']=='Contradiction' for e in training(r)['evidence']))

    def test_unknown_approval_abstains(self):
        r=self.analyse_text('All personnel must complete security awareness training annually.',approval='unknown')
        self.assertEqual(training(r)['automatedFinding'],'Ambiguous')

    def test_duplicate_files_do_not_change_coverage(self):
        with temporary() as directory:
            for name in ('a.txt','b.txt'):
                (directory/name).write_text('All personnel must complete security awareness training annually.')
            r=service.analyse([directory],scope='Two duplicate documents',approval='approved')
            self.assertEqual(len(r['documents']),1)
            self.assertEqual(len(r['scope']['duplicates']),1)
            self.assertEqual(service.summary(r)['assessedScopeCoverage']['numerator'],1)

    def test_rule_schema_rejects_unknown_code_and_deep_groups(self):
        for node in [{'eval':'1+1'},{'pattern':'invented'},{'all':[]},{'phrases':['']},{'all':[{'shell':'cmd'}]}]:
            with self.assertRaises(PolicyError): rules.validate_rule(node)

    def test_unassessed_requirements_remain_in_denominator(self):
        s=service.summary(self.baseline)
        self.assertEqual(s['computable'],1)
        self.assertEqual(s['inScope'],len(self.baseline['requirements']))
        self.assertGreater(s['unassessed'],0)
        self.assertEqual(s['confirmedEvidenceFloor']['numerator'],0)

    def test_canonical_findings_reproduce_without_network(self):
        with patch.object(socket,'create_connection',side_effect=AssertionError('network forbidden')):
            r=service.analyse([ROOT/'examples/policy-review/positive.md'],scope='Synthetic single policy',approval='approved',retention='extracted')
        self.assertEqual(r['canonicalHash'],self.baseline['canonicalHash'])
        self.assertNotEqual(r['runId'],self.baseline['runId'])

    def test_saved_review_does_not_overwrite_automated_finding(self):
        with temporary() as directory:
            path=directory/'review.wacc';store.save(path,self.baseline)
            row=training(self.baseline)
            event=service.review_event(self.baseline,row['id'],'Covered','Checked the source passage','Test reviewer',[a['id'] for a in row['obligations']],[e['id'] for e in row['evidence']])
            store.append_review(path,event)
            with patch.object(corpus,'load',side_effect=AssertionError('must not reload corpus')):
                saved=store.load(path)
                self.assertEqual(saved['run'],self.baseline)
                self.assertEqual(service.summary(saved['run'],saved['events'])['reviewed'],1)
                self.assertIn('Covered',reports.render(saved))

    def test_manual_link_preserves_source_and_review_provenance(self):
        r=deepcopy(self.baseline);row=training(r);doc=r['documents'][0];passage=doc['passages'][-1]
        links=[dict(documentId=doc['id'],passageId=passage['id'],obligationId=a['id']) for a in row['obligations']]
        event=service.review_event(r,row['id'],'Covered','Manual source inspection','Test',[a['id'] for a in row['obligations']],manual_evidence=links)
        self.assertEqual(event['manualEvidence'][0]['excerpt'],passage['text'])
        self.assertEqual(event['identitySource'],'Local self-declared name')

    def test_review_cannot_confirm_without_evidence(self):
        row=training(self.baseline)
        with self.assertRaises(PolicyError):
            service.review_event(self.baseline,row['id'],'Covered','No evidence','Test',[a['id'] for a in row['obligations']])

    def test_new_runs_retain_old_runs_and_require_rereview(self):
        with temporary() as directory:
            path=directory/'runs.wacc';store.save(path,self.baseline)
            row=training(self.baseline)
            event=service.review_event(self.baseline,row['id'],'NotCovered','Rejected evidence','Test')
            store.append_review(path,event)
            changed=deepcopy(self.baseline);changed['runId']=str(uuid.uuid4())
            store.save(path,changed)
            saved=store.load(path)
            self.assertEqual(len(saved['history']),2)
            self.assertEqual(next(r for r in service.apply_reviews(changed,saved['events']) if r['id']==row['id'])['reviewState'],'NeedsReReview')
            self.assertEqual(store.load(path,self.baseline['runId'])['run'],self.baseline)

    def test_historical_finalisation_survives_a_new_run(self):
        with temporary() as directory:
            path=directory/'history.wacc';store.save(path,self.baseline);store.finalise(path)
            new=deepcopy(self.baseline);new['runId']=str(uuid.uuid4());store.save(path,new)
            self.assertFalse(store.load(path)['metadata']['selectedFinalised'])
            old=store.load(path,self.baseline['runId'])
            self.assertTrue(old['metadata']['selectedFinalised'])
            self.assertTrue(reports.model(old)['finalised'])

    def test_secondary_targets_are_independent_manual_findings(self):
        with patch.dict(os.environ,{'WACC_LIBRARY':str(ROOT)}):
            run=service.analyse([ROOT/'examples/policy-review/positive.md'],scope='Secondary example',approval='approved',also=['csf'])
        self.assertTrue(any(r['frameworkId']=='csf' for r in run['requirements']))
        self.assertTrue(all(r['automatedFinding']=='NotAssessed' for r in run['requirements'] if r['frameworkId']=='csf'))
        self.assertEqual(service.summary(run)['computable'],1)

    def test_all_seven_framework_selections_and_practice_counts(self):
        from itertools import combinations
        library = corpus._library()
        with temporary() as directory, patch.dict(os.environ,{'WACC_FRAMEWORK_CACHE':str(directory)}), patch('wacc.policy.corpus._library',return_value=library):
            for size in (1,2,3):
                for keys in combinations(('wa-csp','ism','aescsf'),size):
                    value = corpus.load(keys[0],also=keys[1:])
                    self.assertEqual({f['id'] for f in value['frameworks']},set(keys))
                    self.assertEqual({r['frameworkId'] for r in value['requirements']},set(keys))
                    if 'aescsf' in keys:
                        expected={c.uid for c in library.controls_for('aescsf') if c.depth==2}
                        self.assertEqual({r['id'] for r in value['requirements'] if r['frameworkId']=='aescsf'},expected)

    def test_manual_review_affects_only_its_own_framework(self):
        run = service.analyse([ROOT/'examples/policy-review/positive.md'],scope='Synthetic independence test',approval='approved',retention='extracted',framework='ism',also=['aescsf'])
        row = next(r for r in run['requirements'] if r['frameworkId']=='ism')
        doc=run['documents'][0]; passage=doc['passages'][0]; atom=row['obligations'][0]['id']
        event=service.review_event(run,row['id'],'Covered','Synthetic event used to test separate totals','Test',[atom],manual_evidence=[dict(documentId=doc['id'],passageId=passage['id'],obligationId=atom)])
        values={f['id']:f for f in service.framework_summaries(run,[event])}
        self.assertEqual(values['ism']['reviewerCounts']['Covered'],1)
        self.assertEqual(values['aescsf']['reviewed'],0)
        self.assertEqual(values['aescsf']['confirmedEvidenceFloor']['numerator'],0)
        self.assertTrue(all(r['automatedFinding']=='NotAssessed' for r in run['requirements']))

    def test_report_framework_selection_keeps_saved_run_unchanged(self):
        run = service.analyse([ROOT/'examples/policy-review/positive.md'],scope='Report filters',approval='approved',also=['ism','aescsf'])
        original=deepcopy(run); state=dict(run=run,events=[],metadata={'finalised':False})
        report=reports.model(state,framework_ids=['aescsf'])
        self.assertEqual([f['id'] for f in report['frameworkSummaries']],['aescsf'])
        self.assertTrue(all(r['frameworkId']=='aescsf' for r in report['requirements']))
        self.assertFalse(report['mappings'])
        self.assertEqual(run,original)
        for format in ('html','markdown','csv','json'):
            text=reports.render(state,format,framework_ids=['ism','aescsf'])
            self.assertNotIn('wa-csp:3.2a',text)
            self.assertIn('aescsf',text)
        with self.assertRaises(PolicyError):reports.model(state,framework_ids=['missing'])
        with self.assertRaises(PolicyError):reports.model(state,framework_ids=[])

    def test_changed_publisher_copy_does_not_inherit_training_rule(self):
        row=training(self.baseline)
        source={k:row[k] for k in ('id','frameworkId','officialReference','heading','parentId','authoritativeText','context','sourceLocator')}
        packet=dict(framework={'sourceHash':'changed'},requirements=[source])
        imported=corpus._imported_rows(packet)
        self.assertTrue(all(a['rule'] is None for a in imported[0]['obligations']))

    def test_finalised_run_blocks_review_and_snapshot_is_consistent(self):
        with temporary() as directory:
            path=directory/'original.wacc';copy=directory/'copy.wacc';store.save(path,self.baseline);store.finalise(path)
            with self.assertRaises(PolicyError):
                store.append_review(path,service.review_event(self.baseline,training(self.baseline)['id'],'NotCovered','No','Test'))
            store.snapshot(path,copy)
            self.assertEqual(store.load(path),store.load(copy))

    def test_unknown_schema_and_hostile_sql_objects_are_rejected(self):
        for alteration in ['PRAGMA user_version=999','CREATE TRIGGER evil AFTER INSERT ON events BEGIN DELETE FROM runs; END','CREATE VIEW hostile AS SELECT 1']:
            with temporary() as directory:
                path=directory/'bad.wacc';store.save(path,self.baseline)
                with sqlite3.connect(path) as db: db.execute(alteration)
                db.close()
                with self.assertRaises(PolicyError):store.load(path)

    def test_tampered_evidence_is_rejected(self):
        run=deepcopy(self.baseline);training(run)['evidence'][0]['excerpt']='changed'
        with self.assertRaises(PolicyError):validate_run(run)

    def test_lock_failure_keeps_saved_work(self):
        with temporary() as directory:
            path=directory/'locked.wacc';store.save(path,self.baseline)
            with store.locked(path):
                with self.assertRaises(PolicyError) as caught: store.save(path,self.baseline)
                self.assertEqual(caught.exception.code,6)
            self.assertEqual(store.load(path)['run'],self.baseline)

    def test_failed_atomic_save_does_not_destroy_original(self):
        with temporary() as directory:
            path=directory/'report.html';path.write_text('old')
            with patch('wacc.policy.reports.os.replace',side_effect=OSError('disk full')):
                with self.assertRaises(PolicyError):reports.write_output(path,'new',True)
            self.assertEqual(path.read_text(),'old')

    def test_cancel_before_import_does_not_create_results(self):
        cancel=threading.Event();cancel.set()
        with self.assertRaises(KeyboardInterrupt):
            service.analyse([ROOT/'examples/policy-review/positive.md'],scope='Cancelled',cancel=cancel)

    def test_reports_escape_injection_and_summary_omits_evidence(self):
        state=dict(run=deepcopy(self.baseline),events=[],metadata={'finalised':False})
        state['run']['name']='<script>alert(1)</script>'
        self.assertNotIn('<script>',reports.render(state,'html'))
        state['run']['name']='=HYPERLINK("evil")'
        self.assertIn("'=HYPERLINK",reports.render(state,'csv'))
        self.assertFalse(any(r['evidence'] for r in reports.model(state,False)['requirements']))

    def test_changed_original_is_stale_without_altering_saved_evidence(self):
        with temporary() as directory:
            path=directory/'source.txt';path.write_text('All personnel must complete security awareness training annually.')
            run=service.analyse([path],scope='Selected',approval='approved')
            path.write_text('Changed')
            self.assertIn('Changed',store.verify_sources({'run':run})[0]['status'])
            self.assertNotEqual(training(run)['evidence'][0]['excerpt'],'Changed')

    def test_docx_table_locator_and_external_content_limits(self):
        w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        with temporary() as directory:
            path=directory/'table.docx'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('word/document.xml',f'<w:document xmlns:w="{w}"><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Policy text</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
            doc=documents.extract(path)
            self.assertEqual(doc['passages'][0]['locator']['cell'],1)
            self.assertNotIn('page',doc['passages'][0]['locator'])
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('../escape','unsafe');z.writestr('word/document.xml','<xml/>')
            with self.assertRaises(PolicyError):documents.extract(path)

    def test_failed_document_is_not_assessed_absence(self):
        with temporary() as directory:
            path=directory/'broken.pdf';path.write_bytes(b'not a PDF')
            run=service.analyse([path],scope='Unreadable policy')
            self.assertEqual(run['documents'][0]['status'],'Failed')
            self.assertEqual(training(run)['automatedFinding'],'NotAssessed')

    def test_blank_pdf_remains_an_extraction_limitation(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('Install the pinned PDF dependency to test PDFs')
        with temporary() as directory:
            path=directory/'scan.pdf'
            writer=PdfWriter();writer.add_blank_page(width=612,height=792)
            with path.open('wb') as handle:writer.write(handle)
            run=service.analyse([path],scope='Scanned example')
            self.assertEqual(run['documents'][0]['status'],'Incomplete')
            self.assertEqual(training(run)['automatedFinding'],'NotAssessed')

    def test_pdf_native_text_retains_page_locator(self):
        try:
            from pypdf import PdfWriter
            from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        except ImportError:
            self.skipTest('Install the pinned PDF dependency to test PDFs')
        with temporary() as directory:
            writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 10 Tf 20 700 Td (All personnel must complete security awareness training annually.) Tj ET')
            page[NameObject('/Contents')]=stream
            path=directory/'policy.pdf'
            with path.open('wb') as handle:writer.write(handle)
            run=service.analyse([path],scope='PDF example',approval='approved')
            self.assertEqual(training(run)['automatedFinding'],'FullCandidate')
            self.assertEqual(training(run)['evidence'][0]['locator']['page'],1)

    def test_signed_package_trust_and_tamper_checks(self):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except ImportError:
            self.skipTest('Install signature dependencies to test corpus packages')
        import base64,hashlib
        from wacc.policy import packages
        from wacc.policy.contracts import canonical
        with temporary() as directory:
            key=Ed25519PrivateKey.generate()
            trust=directory/'keys.json';trust.write_text(json.dumps({'keys':{'test-only':{'publicKey':base64.b64encode(key.public_key().public_bytes_raw()).decode()}}}))
            data=corpus.load()
            for r in data['requirements']:
                for a in r['obligations']:
                    if a['rule']:a['reviewStatus']='HumanApproved'
            data['rulesHash']=fingerprint([r['obligations'] for r in data['requirements']])
            payload=canonical(data).encode()
            manifest=canonical(dict(schemaVersion='1.0',version=data['version'],engineMajor=0,files={'corpus.json':hashlib.sha256(payload).hexdigest()},reviewRecord='Synthetic test approval only')).encode()
            signature=canonical(dict(keyId='test-only',algorithm='Ed25519',signature=base64.b64encode(key.sign(manifest)).decode()))
            archive=directory/'test.waccpack'
            def write(body=payload,extra=False):
                with zipfile.ZipFile(archive,'w') as z:
                    z.writestr('manifest.json',manifest);z.writestr('corpus.json',body);z.writestr('signature.json',signature)
                    if extra:z.writestr('execute.py','print(1)')
            write()
            with self.assertRaises(PolicyError):packages.verify(archive)
            with patch.object(packages,'TRUST_FILE',trust):
                self.assertEqual(packages.verify(archive)['signer'],'test-only')
                write(payload+b' ')
                with self.assertRaises(PolicyError):packages.verify(archive)
                write(extra=True)
                with self.assertRaises(PolicyError):packages.verify(archive)

    def test_public_contract_schemas_validate_real_payloads(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest('Install schema validation dependencies')
        for name,value in [('run',self.baseline),('corpus',corpus.load())]:
            schema=json.loads((ROOT/'schemas/policy'/f'{name}.schema.json').read_text(encoding='utf-8'))
            jsonschema.Draft202012Validator.check_schema(schema)
            jsonschema.validate(value,schema)
        with temporary() as directory:
            from wacc.policy.cli import parser,execute
            path=directory/'cli.wacc';store.save(path,self.baseline)
            store.append_review(path,service.review_event(self.baseline,training(self.baseline)['id'],'NotCovered','Rejected','Test'))
            value,_=execute(parser().parse_args(['requirements',str(path),'--format','json']))
            jsonschema.validate(value,json.loads((ROOT/'schemas/policy/cli.schema.json').read_text()))

    def test_report_cannot_replace_assessment_or_original(self):
        state=dict(run=self.baseline,events=[],metadata={'finalised':False})
        with self.assertRaises(PolicyError):
            reports.export_report(state,self.baseline['documents'][0]['path'],'markdown',force=True)
        with self.assertRaises(PolicyError):
            reports.export_report(state,'same.wacc','json',force=True,assessment_path='same.wacc')

    def test_windows_worker_memory_limit_is_enforced(self):
        from wacc.policy.worker_limits import constrain
        code="import sys;sys.stdin.read(1)\ntry: x=bytearray(512*1024*1024)\nexcept MemoryError: print('bounded')"
        process=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        release=constrain(process)
        try:
            output,_=process.communicate(b'x',timeout=10)
            self.assertEqual(output.strip(),b'bounded')
        finally:
            if process.poll() is None:process.kill();process.communicate()
            release()

    def test_cli_json_is_one_value_with_documented_exit_code(self):
        result=subprocess.run([sys.executable,'-m','wacc','analyse',str(ROOT/'examples/policy-review/partial.md'),'--scope','Synthetic CLI','--document-status','approved','--format','json'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,7,result.stderr)
        data=json.loads(result.stdout)
        self.assertEqual(data['schemaVersion'],'1.0')
        self.assertEqual(next(r for r in data['requirements'] if r['id']=='wa-csp:3.2a')['automatedFinding'],'PartialCandidate')

    def test_desktop_uses_saved_services_without_corpus_reanalysis(self):
        import tkinter as tk
        from wacc.policy.desktop import Desktop
        with temporary() as directory:
            path=directory/'desktop.wacc';store.save(path,self.baseline)
            root=tk.Tk();root.withdraw()
            try:
                app=Desktop(root,path);root.update()
                self.assertEqual(app.state['run'],self.baseline)
                app.requirements.selection_set('wa-csp:3.2a');app.select_requirement()
                self.assertIn('annually',app.passage.get('1.0','end'))
                app.relationships();self.assertTrue(app.edges.get_children())
            finally:root.destroy()


if __name__=='__main__':unittest.main()
