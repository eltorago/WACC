"""PRIS wording, commencement boundaries, search and workspace connections."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc import build, control_workspace as workspace, sources
from wacc.io.docx import _paragraph_text
from wacc.loaders import wa_pris
from wacc.model import Corpus
from wacc.registry import FRAMEWORKS_BY_KEY
from wacc.serve import State
from wacc.render.html import render


class PRISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = State()
        cls.corpus = cls.state.corpus

    def test_complete_consolidation_and_independent_review(self):
        records = self.corpus.controls_for('wa-pris')
        self.assertEqual(len(records), 333)
        self.assertEqual(sum(bool(c.text) for c in records), 266)
        self.assertEqual({c.attributes['section'] for c in records if 'section' in c.attributes}, wa_pris.SECTION_NUMBERS)
        self.assertEqual({c.attributes['principle'] for c in records if c.attributes.get('schedule') == 1}, set(range(1, 12)))
        self.assertEqual({c.attributes['principle'] for c in records if c.attributes.get('schedule') == 2}, set(range(1, 6)))
        reviewed = json.loads((ROOT/'data/validation/wa-pris-review.json').read_text(encoding='utf-8'))
        self.assertEqual(reviewed['provisions_compared'], 266)
        self.assertEqual(reviewed['text_sha256'], {c.uid: hashlib.sha256(c.text.encode()).hexdigest() for c in records if c.text})

    def test_clauses_keep_conditions_exceptions_and_nested_lists(self):
        text = self.corpus.control('wa-pris:ipp 4.2').text
        self.assertIn('unless the IPP entity is expressly required or authorised to retain', text)
        text = self.corpus.control('wa-pris:ipp 6.1').text
        self.assertIn('(a) providing access would endanger', text)
        self.assertIn('(ii) denying access is necessary', text)
        self.assertIn('(l) providing access would be likely', text)
        text = self.corpus.control('wa-pris:s 176').text
        self.assertIn('(6) Despite subsection (5)', text)
        self.assertIn('(b) in circumstances prescribed by the regulations.', text)
        self.assertIn('(iv) if the relevant activity is to involve', self.corpus.control('wa-pris:s 170').text)

    def test_schedule_names_do_not_collide(self):
        self.assertIsNone(self.corpus.control('wa-pris:ipp 3.1'))
        sharing = self.corpus.control('wa-pris:rsp 3.1')
        self.assertEqual(sharing.parent_uid, 'wa-pris:rsp 3')
        self.assertIn('re-identified', sharing.text)
        self.assertIn('accurate, complete and up-to-date', self.corpus.control('wa-pris:ipp 3').text)
        self.assertIn('misuse and loss', self.corpus.control('wa-pris:ipp 4.1').text)
        self.assertIn('digital environments', self.corpus.control('wa-pris:rsp 4').text)

    def test_uncommenced_provisions_are_not_current_requirements(self):
        for number in wa_pris.UNCOMMENCED_SECTIONS:
            self.assertIsNone(self.corpus.control('wa-pris:s ' + str(number)))
        for number in (151, 170, 225):
            record = self.corpus.control('wa-pris:s ' + str(number))
            self.assertIn('not yet in force', record.attributes['scope_note'])
        self.assertIn('Part 2 Division 6', ' '.join(self.corpus.frameworks['wa-pris'].notes))

    def test_scope_and_transitions_remain_navigable(self):
        for uid in ('ipp 1.1', 'ipp 7.1', 'ipp 8.1', 'ipp 10.1'):
            self.assertIn('on or after 1 July 2026', self.corpus.control('wa-pris:' + uid).attributes['scope_note'])
        self.assertNotIn('scope_note', self.corpus.control('wa-pris:ipp 4.1').attributes)
        page = render(self.corpus, self.state.payload('PRIS IPP 6.8'), view='cards')
        self.assertIn('wa-pris%3As+27', page)
        self.assertIn('wa-pris%3As+223', page)
        self.assertIn('45 days', page)
        for c in self.corpus.controls_for('wa-pris'):
            for ref in c.attributes.get('legal_context', []):
                self.assertIsNotNone(self.corpus.control(ref['uid']))

    def test_automatic_acquisition_and_changed_source_rejected(self):
        entries, methods = sources.load_catalogue()
        path = sources.local_path(sources.source_directory(), wa_pris.SOURCE_FILE)
        self.assertTrue(sources.matches_review(entries[wa_pris.SOURCE_FILE], path.read_bytes()))
        self.assertEqual(methods[wa_pris.SOURCE_FILE]['method'], 'automatic')
        with patch.object(wa_pris.Path, 'read_bytes', return_value=path.read_bytes() + b'changed'):
            corpus = Corpus()
            fw = copy.deepcopy(FRAMEWORKS_BY_KEY['wa-pris']); corpus.add_framework(fw)
            with self.assertRaisesRegex(ValueError, 'differs from the reviewed'):
                wa_pris.load_into(corpus, fw, path)
            self.assertEqual(corpus.controls, {})

    def test_names_and_exact_identifiers(self):
        for query in ('PRIS', 'WA PRIS Act', 'Privacy and Responsible Information Sharing Act 2024'):
            controls = self.state.payload(query, limit=500).controls
            self.assertEqual(len(controls), 333, query)
            self.assertEqual({c.framework_key for c in controls}, {'wa-pris'})
        for query, uid in [('PRIS IPP 4.1', 'ipp 4.1'), ('PRIS RSP 3.1', 'rsp 3.1'), ('wa-pris:s 79', 's 79')]:
            self.assertEqual([c.uid for c in self.state.payload(query).controls], ['wa-pris:' + uid])

    def test_identifier_labels_and_framework_scope_are_preserved(self):
        from wacc.lookup import IdentifierIndex, Status
        index = IdentifierIndex(self.corpus)
        for query in ('Req 113', 'PSPF Req 113', 'PRIS s 57'):
            self.assertEqual(index.find(query).status, Status.NONE, query)
        self.assertEqual([c.uid for c in index.find('PRIS s 113').matches], ['wa-pris:s 113'])

    def test_privacy_requests_use_case_files_not_account_permissions(self):
        from wacc.derive import derive
        for uid, evidence, source in [('ipp 6.8','case files','si-18'), ('s 79','written impact assessment','ra-8'), ('ipp 1.9','collection notices','pt-3')]:
            result = derive(self.corpus, self.corpus.control('wa-pris:' + uid), self.state.relations)
            self.assertIn(evidence, result.derived_tests[0].text)
            self.assertNotIn('Export effective accounts', result.derived_tests[0].text)
            self.assertNotIn('Inspect the incident plan', result.derived_tests[0].text)
            self.assertIn('nist-800-53:' + source, [m.control.uid for m in result.related_assessments])

    def test_request_response_period_is_a_ceiling(self):
        from wacc.thresholds import stated_by, AT_MOST
        quantities = stated_by(self.corpus.control('wa-pris:ipp 6.8'))
        deadline = next(t for t in quantities if t.value == 45 and t.unit == 'day')
        self.assertEqual(deadline.bound, AT_MOST)

    def test_reviewed_workspace_links_and_scope_export(self):
        refs = [(c['id'], m) for c in workspace.CONTROLS for m in workspace.mappings(c, {'wa-pris'})]
        self.assertEqual(len(refs), 73)
        self.assertEqual(len({key for key, _ in refs}), 16)
        for _, mapping in refs:
            self.assertIsNotNone(self.corpus.control(mapping['uid']))
            self.assertEqual(mapping['provenance'], 'Locally reviewed mapping')
        self.assertEqual({self.corpus.control(m['uid']).attributes['principle'] for _, m in refs if m['uid'].startswith('wa-pris:ipp ')}, set(range(1, 12)))
        self.assertTrue(all(m['relationship']=='Related only' for _,m in refs if m['uid'].startswith('wa-pris:ipp 10.')))
        rows = list(csv.DictReader(io.StringIO(workspace.export_csv({'scope':['1'], 'fw':['wa-pris']}))))
        self.assertEqual(len(rows), 73)
        self.assertTrue(all(r['Source UID'].startswith('wa-pris:') for r in rows))
        self.assertEqual(workspace.matching('wa-pris:ipp 4.1', {'ism'}), [])
        page = workspace.render(self.corpus, {'scope':['1'], 'fw':['wa-pris'], 'control':['PI-03']})
        self.assertIn('WA PRIS Act', page)
        self.assertIn('wa-pris%3Aipp+6.8', page)
        self.assertIn('© State of Western Australia 2026', page)
        self.assertIn('Based on content from the Western Australian Legislation website at 17 September 2026', page)

    def test_missing_source_is_reported(self):
        exists = build._exists
        with patch.object(build, '_exists', side_effect=lambda p: False if str(p).endswith(wa_pris.SOURCE_FILE) else exists(p)):
            corpus, report = build.build(False)
        self.assertIn('wa-pris', report.skipped)
        self.assertEqual(corpus.controls_for('wa-pris'), [])

    def test_word_nonbreaking_hyphens_survive(self):
        paragraph = ET.fromstring('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>de</w:t><w:noBreakHyphen/><w:t>identified</w:t></w:r></w:p>')
        self.assertEqual(_paragraph_text(paragraph), 'de-identified')


if __name__ == '__main__': unittest.main()
