"""Alignment, batch imports and safe ZIP handling without private publisher data."""
from copy import deepcopy
import json
from pathlib import Path
import stat
import sys
import threading
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from test_policy_review import temporary
from wacc.policy import alignment, corpus, documents, reports, service, store
from wacc.policy.cli import parser, execute
from wacc.policy.contracts import PolicyError, canonical_payload, fingerprint, validate_run


def requirement(reference, text, framework='ism'):
    uid = framework + ':' + reference
    return dict(id=uid, frameworkId=framework, officialReference=reference, heading='Synthetic example',
        parentId=None, authoritativeText=text, context='', sourceLocator={'reference':reference},
        obligations=[dict(id='WACC-' + uid, interpretation=text, rule=None, mandatory=True,
                         ruleVersion='1.0', assessmentMethod='ManualReview', reviewStatus='ManualReviewOnly', provenance='Synthetic')])


ROWS = [requirement('ISM-TEST1', 'Multi-factor authentication protects remote access.'),
        requirement('TEST2', 'Backup restoration is tested quarterly.', 'aescsf'),
        requirement('1.1', 'All personnel complete security awareness training annually.', 'wa-csp')]
BASELINE = dict(version='synthetic', requirements=ROWS, mappings=[], rulesHash='synthetic',
    frameworks=[dict(id=key, title=key, edition='Synthetic', extractHash='synthetic') for key in ('ism', 'aescsf', 'wa-csp')])


def document(text, status='Ready'):
    return dict(id='doc', sha256='doc', name='policy.txt', included=True, status=status,
                passages=[dict(id='p1', text=text, locator={'kind':'paragraph', 'paragraph':1})])


class AlignmentTests(unittest.TestCase):
    def test_selective_loader_preserves_controls_and_published_links(self):
        from wacc.build import build
        from wacc.registry import FRAMEWORKS_BY_KEY
        if not (ROOT/'sources/files/ISM_catalog.json').exists():
            self.skipTest('Prepared local corpus needed for loader equivalence.')
        keys = {'wa-csp', 'ism', 'aescsf', 'csf', 'essential-eight'}
        before = deepcopy(FRAMEWORKS_BY_KEY)
        full, _ = build(False)
        with patch('wacc.loaders.extended.scf',side_effect=AssertionError('unselected source loaded')):
            selected, _ = build(False, framework_keys=keys)
        for key in keys:
            self.assertEqual(selected.controls_for(key), full.controls_for(key))
        ids = {c.uid for key in keys for c in selected.controls_for(key)}
        self.assertEqual([link for link in selected.links if link.source_uid in ids and link.target_uid in ids],
                         [link for link in full.links if link.source_uid in ids and link.target_uid in ids])
        self.assertFalse(selected.techniques)
        self.assertFalse(selected.controls_for('scf'))
        self.assertEqual(FRAMEWORKS_BY_KEY, before)

    def test_reference_number_alone_is_not_a_named_framework(self):
        row = requirement('3.2a', 'Backup restoration is tested quarterly.', 'wa-csp')
        self.assertEqual(alignment.compare([row], [document('See section 3.2a.')])[row['id']]['status'], 'Not mentioned')

    def test_review_views_do_not_modify_saved_events(self):
        run = dict(runId='run', requirements=[dict(id='one', applicability='InScope', reviewState='Pending', reviewerFinding=None)])
        events = [dict(runId='run', requirementId='one', finding='NotCovered', reason='Preserve this')]
        rows = service.apply_reviews(run, events)
        rows[0]['review'].pop('reason')
        self.assertEqual(events[0]['reason'], 'Preserve this')
        self.assertEqual(run['requirements'][0]['reviewState'], 'Pending')

    def test_distinct_topics_and_unmentioned_requirements(self):
        results = alignment.compare(ROWS, [document('MFA protects remote access. Backup restoration is tested quarterly.')])
        self.assertEqual(results['ism:ISM-TEST1']['status'], 'Mentioned')
        self.assertEqual(results['aescsf:TEST2']['status'], 'Mentioned')
        self.assertEqual(results['wa-csp:1.1']['status'], 'Not mentioned')
        self.assertEqual(results['ism:ISM-TEST1']['matches'][0]['matchedTerms'], ['MFA', 'access', 'protects', 'remote'])

    def test_other_frameworks_do_not_change_a_requirements_status(self):
        target=ROWS[0]
        doc=document('MFA protects remote access.')
        extra=[requirement('COPY'+str(i),'Remote access is restricted to authorised users.','other') for i in range(20)]
        self.assertEqual(alignment.compare([target],[doc])[target['id']],
                         alignment.compare([target,*extra],[doc])[target['id']])

    def test_parent_context_alone_cannot_make_a_clear_match(self):
        row=dict(ROWS[0],context='The disaster recovery plan restores services after a severe disruption.')
        result=alignment.compare([row],[document(row['context'])])[row['id']]
        self.assertNotEqual(result['status'],'Mentioned')

    def test_negative_and_qualified_wording_is_not_a_strong_match(self):
        for text in ('MFA does not protect remote access.', 'MFA may protect remote access.', 'MFA protection is disabled for remote access.'):
            result = alignment.compare(ROWS, [document(text)])['ism:ISM-TEST1']
            self.assertEqual(result['status'], 'Related wording')
            self.assertTrue(result['matches'][0]['cautions'])

    def test_annual_training_wording_variants_match(self):
        row = dict(ROWS[2], authoritativeText='cyber security awareness training on an annual basis',
                   context='Each entity must ensure that its personnel undertake:')
        result = alignment.compare([row], [document('All personnel must complete cyber security awareness training annually.')])[row['id']]
        self.assertEqual(result['status'], 'Mentioned')

    def test_generic_security_words_do_not_match_unrelated_requirements(self):
        result = alignment.compare(ROWS, [document('Our information security policy establishes appropriate systems and controls.')])
        self.assertEqual({r['status'] for r in result.values()}, {'Not mentioned'})

    def test_unrelated_sentences_are_not_joined(self):
        result = alignment.compare(ROWS[:1], [document('Access to the kitchen is remote. Staff know about authentication.')])
        self.assertEqual(result[ROWS[0]['id']]['status'], 'Not mentioned')

    def test_named_reference_is_a_reference_not_coverage(self):
        result = alignment.compare(ROWS, [document('Refer to ISM-TEST1.')])['ism:ISM-TEST1']
        self.assertEqual(result['status'], 'Related wording')
        self.assertEqual(result['matches'][0]['reason'], 'Named framework reference')

    def test_unreadable_or_unretained_text_cannot_establish_absence(self):
        for doc in (document('Nothing relevant.', 'Incomplete'), dict(document('Nothing relevant.'), extractedPassageCount=4)):
            self.assertEqual({r['status'] for r in alignment.compare(ROWS, [doc]).values()}, {'Unable to check'})

    def test_no_included_documents_cannot_establish_absence(self):
        doc = dict(document('MFA protects remote access.'), included=False)
        self.assertEqual({r['status'] for r in alignment.compare(ROWS, [doc]).values()}, {'Unable to check'})

    def test_results_retain_exact_unicode_text_and_offsets(self):
        text = 'Preface. ＭＦＡ protects remote access.'
        match = alignment.compare(ROWS, [document(text)])['ism:ISM-TEST1']['matches'][0]
        self.assertEqual(match['excerpt'], text[match['start']:match['end']])
        self.assertIn('ＭＦＡ', [match['excerpt'][s['start']:s['end']] for s in match['matchedSpans']])

    def test_large_paragraph_does_not_duplicate_unmatched_text_in_each_result(self):
        text='Unrelated introductory text. '*1000 + 'MFA protects remote access.'
        match=alignment.compare(ROWS,[document(text)])['ism:ISM-TEST1']['matches'][0]
        self.assertLessEqual(len(match['excerpt']),1600)
        self.assertEqual(match['excerpt'],text[match['start']:match['end']])

    def test_reproducible_results_and_match_count(self):
        docs = [dict(document('MFA protects remote access.'), id='d'+str(i), sha256='d'+str(i)) for i in range(8)]
        first = alignment.compare(ROWS, docs)
        self.assertEqual(first, alignment.compare(ROWS, list(reversed(docs))))
        self.assertEqual(first['ism:ISM-TEST1']['matchCount'], 8)
        self.assertEqual(len(first['ism:ISM-TEST1']['matches']), 5)

    def test_cancelled_comparison_stops(self):
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(KeyboardInterrupt):
            alignment.compare(ROWS, [document('MFA protects remote access.')], cancel)

    def test_multi_file_and_zip_are_equivalent_and_deduplicated(self):
        with temporary() as directory, patch.object(corpus, 'load', return_value=deepcopy(BASELINE)):
            first, second = directory/'access.txt', directory/'backup.md'
            first.write_text('MFA protects remote access.', encoding='utf-8')
            second.write_text('Backup restoration is tested quarterly.', encoding='utf-8')
            archive = directory/'policies.zip'
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.write(first, 'department/access.txt')
                zipped.write(second, 'department/backup.md')
                zipped.writestr('logo.png', b'image')
            loose = service.analyse([first, second], scope='Batch')
            zipped = service.analyse([archive, first], scope='Batch')
            self.assertEqual(len(zipped['documents']), 2)
            self.assertEqual(len(zipped['scope']['duplicates']), 1)
            self.assertEqual(len(zipped['scope']['skippedInputs']), 1)
            self.assertEqual(zipped['scope']['mode'], 'PolicySet')
            self.assertEqual([r['alignment']['status'] for r in loose['requirements']],
                             [r['alignment']['status'] for r in zipped['requirements']])
            self.assertTrue(any(d.get('archiveMember') for d in zipped['documents']))
            self.assertFalse((directory/'department').exists())
            path = directory/'saved.wacc'; store.save(path, zipped)
            state = store.load(path)
            self.assertTrue(all(s['status']=='Unchanged' for s in store.verify_sources(state)))
            self.assertEqual(state['run'], zipped)
            archive.write_bytes(b'changed archive')
            self.assertTrue(any(s['status'].startswith('Changed') for s in store.verify_sources(state)))

    def test_unsafe_archives_are_rejected_before_parsing(self):
        with temporary() as directory:
            for name in ('../escape.txt', '/absolute.txt', 'C:/drive.txt', 'folder\\file.txt'):
                path = directory/'unsafe.zip'
                with zipfile.ZipFile(path, 'w') as zipped:
                    zipped.writestr(name, 'MFA protects remote access.')
                if '\\' in name:
                    path.write_bytes(path.read_bytes().replace(b'folder/file.txt', b'folder\\file.txt'))
                with self.subTest(name=name), self.assertRaises(PolicyError):
                    documents.expand_inputs([path])
            with zipfile.ZipFile(path, 'w') as zipped:
                entry = zipfile.ZipInfo('link.txt'); entry.create_system=3
                entry.external_attr=(stat.S_IFLNK | 0o777) << 16
                zipped.writestr(entry, 'elsewhere.txt')
            with self.assertRaises(PolicyError): documents.expand_inputs([path])

    def test_zip_expansion_file_count_and_nested_archive_limits(self):
        with temporary() as directory:
            path=directory/'limits.zip'
            with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as zipped:
                zipped.writestr('bomb.txt', 'x'*1_000_000)
            with self.assertRaises(PolicyError): documents.expand_inputs([path])
            with zipfile.ZipFile(path,'w') as zipped:
                for i in range(251): zipped.writestr(str(i)+'.txt','text')
            with self.assertRaises(PolicyError): documents.expand_inputs([path])
            with zipfile.ZipFile(path,'w') as zipped: zipped.writestr('nested.zip', b'zip')
            with self.assertRaises(PolicyError): documents.expand_inputs([path])

    def test_corrupt_member_is_reported_and_other_files_are_preserved(self):
        with temporary() as directory, patch.object(corpus, 'load', return_value=deepcopy(BASELINE)):
            path=directory/'mixed.zip'
            with zipfile.ZipFile(path,'w') as zipped:
                zipped.writestr('good.txt','MFA protects remote access.')
                zipped.writestr('broken.pdf',b'not a PDF')
            run=service.analyse([path],scope='Mixed files')
            self.assertEqual({d['status'] for d in run['documents']}, {'Ready','Failed'})
            self.assertEqual(run['requirements'][0]['alignment']['status'],'Mentioned')
            self.assertEqual(run['requirements'][1]['alignment']['status'],'Unable to check')
            validate_run(run)

    def test_report_filters_and_redaction_preserve_original_data(self):
        with temporary() as directory, patch.object(corpus, 'load', return_value=deepcopy(BASELINE)):
            path=directory/'policy.txt'; path.write_text('MFA protects remote access.\n\nPrivate heading <script>alert(1)</script>',encoding='utf-8')
            run=service.analyse([path],scope='Synthetic'); state=dict(run=run,events=[],metadata={})
            original=deepcopy(state)
            summary=reports.model(state,False,['ism'])
            self.assertFalse(summary['requirements'][0]['alignment']['matches'])
            self.assertEqual(summary['requirements'][0]['alignment']['status'],'Mentioned')
            self.assertEqual(state,original)
            for format in ('html','markdown','csv','json'):
                content=reports.render(state,format,framework_ids=['ism'])
                self.assertIn('ISM-TEST1',content.replace('\\',''))
                self.assertNotIn('aescsf:TEST2',content)
            self.assertNotIn('<script>',reports.render(state,'html'))

    def test_alignment_source_tampering_is_detected_even_with_new_run_hash(self):
        with temporary() as directory, patch.object(corpus, 'load', return_value=deepcopy(BASELINE)):
            path=directory/'policy.txt';path.write_text('MFA protects remote access.',encoding='utf-8')
            run=service.analyse([path],scope='Synthetic')
            run['requirements'][0]['alignment']['matches'][0]['excerpt']='Invented passage'
            run['canonicalHash']=fingerprint(canonical_payload(run))
            with self.assertRaises(PolicyError):validate_run(run)

    def test_compare_cli_and_saved_commands_return_alignment(self):
        with temporary() as directory, patch.object(corpus, 'load', return_value=deepcopy(BASELINE)):
            source=directory/'policy.txt';source.write_text('MFA protects remote access.',encoding='utf-8')
            saved=directory/'comparison.wacc'
            data,code=execute(parser().parse_args(['compare',str(source),'--scope','Synthetic','--assessment',str(saved)]))
            self.assertEqual(code,0)
            self.assertEqual(data['reportType'],'FrameworkAlignment')
            gaps,_=execute(parser().parse_args(['gaps',str(saved)]))
            self.assertEqual({r['id'] for r in gaps['requirements']},{'aescsf:TEST2','wa-csp:1.1'})
            with patch('wacc.policy.reports.render', wraps=reports.render) as render:
                execute(parser().parse_args(['report',str(saved),'--output',str(directory/'report.html')]))
                self.assertEqual(render.call_count,1)

    def test_desktop_selection_reuses_alignment_and_indexes(self):
        import tkinter as tk
        from wacc.policy.desktop import Desktop
        with temporary() as directory, patch.object(corpus,'load',return_value=deepcopy(BASELINE)):
            source=directory/'policy.txt';source.write_text('MFA protects remote access.',encoding='utf-8')
            run=service.analyse([source],scope='Synthetic'); saved=directory/'ui.wacc';store.save(saved,run)
            root=tk.Tk();root.withdraw()
            try:
                with patch.object(corpus,'installed',return_value={}):app=Desktop(root,saved)
                with patch.object(alignment,'compare',side_effect=AssertionError('do not compare on selection')):
                    app.requirements.selection_set('ism:ISM-TEST1');app.select_requirement()
                    self.assertIn('MFA',app.passage.get('1.0','end'))
                    app.filter.set('Not mentioned')
                    self.assertFalse(app.requirements.exists('ism:ISM-TEST1'))
                    self.assertTrue(app.requirements.exists('wa-csp:1.1'))
            finally:root.destroy()


if __name__=='__main__':unittest.main()
