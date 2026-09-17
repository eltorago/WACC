"""Principles remain complete, independently selectable and counted once."""
from collections import Counter
import copy
import csv
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc import build, control_workspace as workspace, framework_families, sources
from wacc.loaders import oscal, principles
from wacc.model import Corpus
from wacc.registry import FRAMEWORKS_BY_KEY
from wacc.serve import State
from tools.review_asd_principles import compare


class PrinciplesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.state = State()

    def test_principles_are_partitioned_without_duplicate_records(self):
        corpus = self.state.corpus
        records = corpus.controls_for('asd-principles')
        self.assertEqual(len(records), 49)
        self.assertEqual(Counter(c.attributes['function'] for c in records),
                         dict(Govern=14, Identify=6, Protect=17, Detect=5, Respond=5, Recover=2))
        self.assertEqual(len(corpus.controls_for('ism')), 1143)
        self.assertEqual(len(corpus.controls), 7395)
        self.assertEqual(framework_families.count(['ism', 'asd-principles']), 1)
        self.assertFalse(any(c.attributes.get('class') == 'ISM-principle' for c in corpus.controls_for('ism')))
        self.assertEqual([c.identifier for c in records], list(principles.IDENTIFIERS))

    def test_full_publisher_statements_match_page_and_reviewed_hashes(self):
        folder = sources.source_directory()
        catalog = oscal.load_catalog(str(sources.local_path(folder, 'ISM_catalog.json')))
        page = sources.local_path(folder, 'asd-cyber-security-principles-2026-09.html').read_bytes()
        records = compare(page, catalog)
        self.assertEqual(len(records), 49)
        review = json.loads((ROOT/'data/validation/asd-principles-review.json').read_text(encoding='utf-8'))
        import hashlib
        for c in self.state.corpus.controls_for('asd-principles'):
            self.assertEqual(hashlib.sha256(c.text.encode()).hexdigest(), review['principle_text_sha256'][c.identifier])
        with self.assertRaises(ValueError): compare(page.replace(b'GOV-01', b'GOV-99'), catalog)
        with self.assertRaises(ValueError): compare(page.replace(b'accountable for cyber security.', b'responsible for cyber security.'), catalog)

    def test_incomplete_partition_fails_before_mutating_the_corpus(self):
        corpus = Corpus()
        for key in ('ism','asd-principles'): corpus.add_framework(copy.deepcopy(FRAMEWORKS_BY_KEY[key]))
        c = copy.deepcopy(self.state.corpus.controls_for('asd-principles')[0])
        c.framework_key = 'ism'; corpus.add_control(c)
        before = set(corpus.controls)
        with self.assertRaises(ValueError): principles.partition(corpus, corpus.frameworks['asd-principles'])
        self.assertEqual(set(corpus.controls), before)
        self.assertEqual(corpus.control_aliases, {})

    def test_exact_names_and_old_ism_links_resolve(self):
        for query in ('asd principles', 'ASD Cyber Security Principles', 'cyber security principles', 'ISM principles'):
            hits = self.state.index.search(query, limit=100).hits
            self.assertEqual(len(hits), 49, query)
            self.assertEqual({h.control.framework_key for h in hits}, {'asd-principles'})
        for query in ('ism:gov-1', 'ISM:GOV-01', 'ASD GOV-01', 'asd-principles:GOV-01'):
            self.assertEqual([c.uid for c in self.state.payload(query).controls], ['asd-principles:gov-1'], query)
        self.assertEqual([c.uid for c in self.state.payload('ism:ism-1507').controls], ['ism:ism-1507'])
        from wacc.render.html import render
        page = render(self.state.corpus, self.state.payload('ASD principles', limit=50))
        self.assertNotIn('No known subject matched this', page)

    def test_workspace_scope_and_exports_use_reviewed_principle_links(self):
        only = {'asd-principles'}
        all_refs = [m for c in workspace.CONTROLS for m in workspace.mappings(c, only)]
        self.assertEqual(len(all_refs), 101)
        self.assertEqual({m['uid'] for m in all_refs}, {c.uid for c in self.state.corpus.controls_for('asd-principles')})
        self.assertTrue(all(m['provenance']=='Locally reviewed mapping' for m in all_refs))
        self.assertTrue(all(m['relationship']=='Related only' for m in all_refs if m['uid'] in ('asd-principles:gov-8', 'asd-principles:pro-17')))
        self.assertIn('PA-01', {c['id'] for c in workspace.matching('PRO-12', only)})
        page = workspace.render(self.state.corpus, {'control':['PA-01'],'scope':['1'],'fw':['asd-principles']})
        self.assertIn('ASD Cyber Security Principles', page)
        self.assertIn('asd-principles%3Apro-12', page)
        rows = list(csv.DictReader(io.StringIO(workspace.export_csv({'scope':['1'],'fw':['asd-principles']}))))
        self.assertEqual(len(rows), 101)
        self.assertTrue(all(r['Source UID'].startswith('asd-principles:') for r in rows))
        self.assertEqual(workspace.matching('asd-principles:pro-12', {'ism'}), [])

    def test_shared_source_unavailable_marks_both_frameworks_missing(self):
        exists = build._exists
        with patch.object(build, '_exists', side_effect=lambda path: False if str(path).endswith('ISM_catalog.json') else exists(path)):
            corpus, report = build.build(False)
        self.assertIn('ism', report.skipped)
        self.assertIn('asd-principles', report.skipped)
        self.assertEqual(corpus.controls_for('asd-principles'), [])

    def test_source_acquisition_reuses_the_official_catalogue(self):
        permissions, methods = sources.load_catalogue()
        framework = FRAMEWORKS_BY_KEY['asd-principles']
        self.assertEqual(framework.source_file, 'ISM_catalog.json')
        for name in (framework.source_file, *framework.source_files):
            self.assertEqual(methods[name]['method'], 'automatic')
            self.assertTrue(sources.matches_review(permissions[name], sources.local_path(sources.source_directory(), name).read_bytes()))


if __name__ == '__main__': unittest.main()
