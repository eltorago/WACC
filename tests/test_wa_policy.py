"""2026 policy extraction, edition migration and workspace references."""
import copy
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import shutil
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc import wa_policy, sources
from wacc.loaders.wa import load_policy
from wacc.model import Corpus
from wacc.registry import FRAMEWORKS_BY_KEY
from wacc.relate import Relations


@contextmanager
def workspace_temp():
    folder = ROOT / ('.wacc-test-' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        assert folder.resolve().parent == ROOT.resolve()
        shutil.rmtree(folder)


class ParserTests(unittest.TestCase):
    def test_wrapped_compounds_and_urls(self):
        self.assertEqual(wa_policy.clean_wrapping('off- network; non- production; e- recruitment'),
                         'off-network; non-production; e-recruitment')
        self.assertEqual(wa_policy.clean_wrapping('security- and privacy-related'), 'security- and privacy-related')
        self.assertEqual(wa_policy.clean_wrapping('https://irp.dpc.wa.gov. au.'), 'https://irp.dpc.wa.gov.au.')

    def test_nested_roman_lists_and_changed_introductions(self):
        section = dict(number='2.2', title='Risk', page=16, body=[
            ('The programme should consider:', 80, 16),
            ('a. First risk', 80, 16), ('i. Nested item', 98, 16),
            ('ii. Another nested item', 98, 16),
            ('b. Second risk', 80, 16),
            ('Reassess when:', 80, 16), ('c. Circumstances change', 80, 17),
            ('Section note.', 80, 17)])
        rows = wa_policy.records_for(section)
        self.assertEqual([r['identifier'] for r in rows], ['2.2a','2.2b','2.2c'])
        self.assertIn('ii. Another nested item', rows[0]['text'])
        self.assertEqual(rows[2]['lead_in'], 'Reassess when:')
        self.assertEqual(rows[2]['page'], 17)
        self.assertEqual(section['notes'], 'Section note.')
        self.assertNotIn('Section note', rows[2]['text'])

    def test_broken_letter_sequence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'clause sequence'):
            wa_policy.records_for(dict(number='3.1', title='Control', page=1,
                body=[('a. First',80,1),('c. Missing second',80,1)]))

    def test_unreviewed_pdf_cannot_replace_old_cache(self):
        with workspace_temp() as tmp:
            cache, source = Path(tmp)/'wa.json', Path(tmp)/'policy.pdf'
            cache.write_text('{"edition":"2024"}', encoding='utf-8')
            source.write_bytes(b'not the reviewed PDF')
            with self.assertRaisesRegex(ValueError, 'differs from the reviewed'):
                wa_policy.ensure_current(cache, source)
            self.assertEqual(json.loads(cache.read_text())['edition'], '2024')

    def test_old_cache_requires_current_source(self):
        with workspace_temp() as tmp:
            cache = Path(tmp)/'wa.json'
            cache.write_text('{"edition":"2024"}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Download the 2026'):
                wa_policy.ensure_current(cache, Path(tmp)/'missing.pdf')
            corpus = Corpus()
            fw = copy.deepcopy(FRAMEWORKS_BY_KEY['wa-csp'])
            corpus.add_framework(fw)
            with self.assertRaisesRegex(ValueError, 'Re-extract'):
                load_policy(corpus, fw, str(cache))
            self.assertEqual(corpus.controls, {})

    def test_missing_pdf_dependency_has_actionable_message(self):
        with workspace_temp() as tmp:
            source = Path(tmp)/'policy.pdf'
            source.write_bytes(b'present')
            with patch.object(wa_policy, 'parse', side_effect=ImportError):
                with self.assertRaisesRegex(ValueError, 'pip install pdfplumber'):
                    wa_policy.ensure_current(Path(tmp)/'wa.json',source)


class ReviewedPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = sources.local_path(sources.source_directory(), 'wa-cyber-security-policy.pdf')
        if not cls.source.exists():
            raise unittest.SkipTest('Acquire the reviewed 2026 policy to run source integration tests')
        cls.data = wa_policy.parse(cls.source)
        cls.rows = {r['identifier']:r for r in cls.data['records']}
        cls.temp = workspace_temp()
        folder = cls.temp.__enter__()
        cls.addClassCleanup(cls.temp.__exit__, None, None, None)
        cls.cache = folder/'wa.json'
        wa_policy.write_cache(cls.cache,cls.data)
        cls.corpus = Corpus()
        cls.framework = copy.deepcopy(FRAMEWORKS_BY_KEY['wa-csp'])
        cls.corpus.add_framework(cls.framework)
        load_policy(cls.corpus,cls.framework,str(cls.cache))
        cls.relations = Relations(cls.corpus)

    def test_complete_structure_and_no_duplicate_identifiers(self):
        self.assertEqual(self.data['page_count'],44)
        self.assertEqual(len(self.data['contents_sections']),58)
        self.assertEqual(len(self.rows),218)
        self.assertEqual(len(self.corpus.controls),262)
        for n in range(1,15): self.assertIn('3.1.'+str(n),self.data['contents_sections'])
        self.assertIn('3.14.3f',self.rows)
        self.assertEqual(self.corpus.control('wa-csp:3.1.3a').parent_uid,'wa-csp:3.1.3')
        self.assertEqual(self.corpus.control('wa-csp:3.1.3').parent_uid,'wa-csp:3.1')
        self.assertEqual(self.corpus.control('wa-csp:3.1').parent_uid,'wa-csp:3')
        self.assertIn('prompt injection',self.rows['3.14.3a']['text'])
        self.assertIn('iv.',self.rows['3.1.13b']['text'])
        self.assertNotIn('2026 WA Government Cyber Security Policy |',str(self.rows))

    def test_reporting_clocks_and_transition_dates_are_preserved(self):
        report = self.relations.quotable_text('wa-csp:5.1a')
        plan = self.relations.quotable_text('wa-csp:5.2c')
        self.assertIn('6 hours',report)
        self.assertIn('12 hours of detection',report)
        self.assertIn('12 hours of confirmation',plan)
        self.assertIn('December 2028',self.rows['3']['text'])
        self.assertIn('December 2027',self.rows['3.12']['text'])
        self.assertIn('end of 2027',self.rows['3.1.1d']['text'])
        self.assertEqual(self.rows['5.1a']['page'],32)
        self.assertFalse(self.corpus.control('wa-csp:5.1').attributes.get('structural'))

    def test_reassessment_keeps_its_own_introductory_sentence(self):
        quote = self.relations.quotable_text('wa-csp:2.2e')
        self.assertTrue(quote.startswith('Risk should be reassessed'))
        self.assertNotIn('take account of',quote)

    def test_catalogue_matches_reviewed_edition(self):
        permissions, methods = sources.load_catalogue()
        name = self.source.name
        self.assertTrue(sources.matches_review(permissions[name],self.source.read_bytes()))
        self.assertIn('/2026-10/', methods[name]['urls'][0])
        self.assertIn('2026',self.framework.revision)

    def test_all_workspace_references_resolve_to_2026(self):
        mappings=json.loads((ROOT/'data/workspace-frameworks.json').read_text(encoding='utf-8'))
        ids=set()
        for path in (ROOT/'data/library').glob('*.json'):
            for control in json.loads(path.read_text(encoding='utf-8')).get('controls',[]):
                ids.add(control['id'])
                mappings.setdefault(control['id'],[]).extend(control.get('mappings',[]))
        for control,links in mappings.items():
            for link in links:
                if link.get('uid', '').startswith('wa-csp:'):
                    self.assertIn(control,ids)
                    record=self.corpus.control(link['uid'])
                    self.assertIsNotNone(record,(control,link))
                    self.assertEqual(record.attributes['edition'],'2026')
        self.assertIn('wa-csp:3.1.5d',[r['uid'] for r in mappings['AP-02']])
        self.assertIn('wa-csp:3.8c',[r['uid'] for r in mappings['PW-02']])
        self.assertIn('wa-csp:3.6',[r['uid'] for r in mappings['MD-01']])
        self.assertIn('wa-csp:5.4',[r['uid'] for r in mappings['IR-03']])

    def test_old_cache_is_rebuilt_and_current_cache_is_reused(self):
        with workspace_temp() as tmp:
            cache=Path(tmp)/'wa.json'
            cache.write_text('{"edition":"2024"}',encoding='utf-8')
            with patch.object(wa_policy,'parse',return_value=self.data) as parse:
                wa_policy.ensure_current(cache,self.source)
                parse.assert_called_once()
            self.assertEqual(json.loads(cache.read_text(encoding='utf-8'))['edition'],'2026')
            with patch.object(wa_policy,'parse',side_effect=AssertionError('unnecessary parse')):
                wa_policy.ensure_current(cache,self.source)


if __name__ == '__main__': unittest.main()
