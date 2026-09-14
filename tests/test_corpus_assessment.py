"""Assessment scope and corpus attribution regressions."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc.serve import State
from wacc.derive import derive
from wacc.model import Provenance
from wacc.render import html


class CorpusAssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = State()

    def result(self, uid):
        s = self.state
        return derive(s.corpus, s.corpus.control(uid), s.relations)

    def test_privileged_request_uses_approval_evidence_and_corpus_methods(self):
        result = self.result('ism:ism-1507')
        text = result.derived_tests[0].text
        self.assertIn('activation date', text)
        self.assertIn('before validation', text)
        refs = {m.control.uid: m for m in result.related_assessments}
        for uid in ['nist-800-53:ac-2', 'nist-800-53:ac-6.5']:
            self.assertIn(uid, refs)
            self.assertEqual(refs[uid].connection, Provenance.DERIVED)
            for statement in refs[uid].statements:
                self.assertEqual(statement.provenance, Provenance.PUBLISHED)
                self.assertEqual(statement.control_uid, uid)
                self.assertIn(statement, self.state.corpus.statements_for(uid))
        self.assertEqual(result.published, [])

    def test_log_protection_does_not_test_collection_or_retention(self):
        result = self.result('ism:ism-1985')
        text = result.derived_tests[0].text
        self.assertIn('alteration and deletion', text)
        self.assertNotIn('Generate an authorised benign test event', text)
        self.assertNotIn('retention', text.lower())
        self.assertIn('nist-800-53:au-9', [m.control.uid for m in result.related_assessments])
        self.assertIn('hide what happened', result.risk.text)

    def test_related_material_is_navigable_and_attributed(self):
        result = self.result('ism:ism-1507')
        panel = html.control_panel(self.state.corpus, result)
        self.assertIn('q=nist-800-53%3Aac-2', panel)
        self.assertIn('Connection: derived', panel)
        self.assertIn('NIST SP 800-53A', panel)
        self.assertIn('Examine:', panel)
        self.assertIn('Interview:', panel)
        self.assertIn('Test:', panel)
        self.assertNotIn('uplift', panel.lower())

    def test_own_published_methods_remain_unchanged(self):
        result = self.result('nist-800-53:ac-6')
        self.assertEqual(result.published, self.state.corpus.statements_for('nist-800-53:ac-6'))
        self.assertNotIn('nist-800-53:ac-6', [m.control.uid for m in result.related_assessments])


if __name__ == '__main__':
    unittest.main()
