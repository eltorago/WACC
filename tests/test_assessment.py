"""Behaviour checks for combined results and assessment guidance."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wacc.serve import State
from wacc.derive import derive
from wacc.model import Control, Provenance, Tier
from wacc.render import html, export
from wacc.render.groups import result_groups
from wacc.assessment import guidance


class AssessmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = State(verbose=False)

    def test_governance_controls_share_outcome_group_without_changing_authority(self):
        payload = self.state.payload('cyber security')
        groups = result_groups(payload)
        original = [c.uid for c in payload.controls]
        combined = [c.uid for b in groups for cov in b.coverage for c in cov.controls]
        self.assertCountEqual(combined, original)
        self.assertEqual(len(combined), len(set(combined)))
        self.assertEqual(len(groups), 3)
        tiers = {c.framework.tier for c in groups[0].coverage}
        self.assertTrue({Tier.STATUTE, Tier.MANDATED_POLICY, Tier.OUTCOME} <= tiers)
        page = html.render(self.state.corpus, payload, view='grid')
        self.assertIn('Outcomes / maturity', page)
        self.assertNotIn('Tier 1', page)
        self.assertNotIn('Tier 2', page)

    def test_topic_assessments_have_operational_checks(self):
        examples = [('Multi-factor authentication is required', 'legacy authentication'),
                    ('Backups are tested', 'isolated environment'),
                    ('Security patches are applied', 'rescan result'),
                    ('Event logs are retained', 'oldest available records'),
                    ('Encryption is used', 'key access')]
        for text, evidence in examples:
            with self.subTest(text=text):
                risk, assessment = guidance(text, 'outcome')
                self.assertIn(evidence, assessment)
                self.assertLess(len(risk.split()), 40)
                self.assertNotIn('outcome is not achieved', risk)

    def test_unrelated_words_do_not_trigger_topic_guidance(self):
        for text in ['Logical separation is maintained', 'An annual report is prepared',
                     'Password recovery is controlled']:
            risk, _ = guidance(text, 'document')
            self.assertNotIn('relevant security events', risk)
            self.assertNotIn('incident escalation', risk)
            self.assertNotIn('recovery arrangements', risk)

    def test_risk_is_displayed_verbatim_without_archetype_or_extra_sentences(self):
        control = Control('ism', 'sample', 'Multi-factor authentication is required.')
        result = derive(self.state.corpus, control)
        expected, _ = guidance(control.text, 'access')
        self.assertEqual(result.risk.text, expected)
        block = html._risk_block(result.risk)
        self.assertIn(expected, block)
        self.assertNotIn('What that means here', block)
        self.assertNotIn('More people can reach', block)
        self.assertEqual(result.risk.provenance, Provenance.DERIVED)
        assessment = result.derived_tests[0].text
        for phrase in ['Acceptance criteria:', 'evidence references', 'result for each acceptance criterion', 'follow-up']:
            self.assertIn(phrase, assessment)

    def test_no_classifier_commentary_in_panel_or_plan(self):
        payload = self.state.payload('backups')
        derivations = {c.uid: derive(self.state.corpus, c) for c in payload.controls}
        plan = export.test_plan(self.state.corpus, payload, derivations)
        panels = ''.join(html.control_panel(self.state.corpus, d) for d in derivations.values())
        for phrase in ['Shape:', 'Why that shape:', 'default archetype', 'state of affairs holds']:
            self.assertNotIn(phrase, plan + panels)


if __name__ == '__main__':
    unittest.main()
