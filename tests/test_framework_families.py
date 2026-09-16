"""E8 remains navigable without becoming a second set of broad strategies."""
import csv
import io
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wacc import framework_families as families, control_workspace as workspace
from wacc.serve import State
from wacc.framework_review import render as framework_review


class FrameworkFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.state=State()

    def test_raw_sources_retained_but_family_count_is_one(self):
        self.assertEqual(families.count(['asd-strategies','essential-eight']),1)
        corpus=self.state.corpus
        broad=corpus.controls_for('asd-strategies');detail=corpus.controls_for('essential-eight')
        self.assertEqual((len(broad),len(detail)),(37,304))
        self.assertEqual(len(families.preferred_uids(c.uid for c in broad+detail)),333)
        self.assertEqual(len(families.preferred_uids(c.uid for c in broad)),37)
        self.assertEqual(len(families.preferred_uids(c.uid for c in detail)),304)

    def test_each_maturity_group_resolves_to_its_broader_strategy(self):
        corpus=self.state.corpus
        targets={families.strategy_uid(c.uid) for c in corpus.controls_for('essential-eight')}
        self.assertEqual(len(targets),8)
        self.assertTrue(all(corpus.control(uid) for uid in targets))
        self.assertEqual(families.strategy_uid('essential-eight:ml1-rb-1'),'asd-strategies:s34')

    def test_topic_results_prefer_detail_and_exact_links_retain_broad_source(self):
        result=self.state.index.search('application control',limit=500,compose=False)
        ids={hit.control.uid for hit in result.hits}
        self.assertTrue(any(uid.startswith('essential-eight:') for uid in ids))
        self.assertEqual(ids,families.preferred_uids(ids))
        exact=self.state.payload('asd-strategies:s01')
        self.assertEqual([c.uid for c in exact.controls],['asd-strategies:s01'])
        for term in ('essential eight','e8','essential 8'):
            self.assertEqual({h.control.framework_key for h in self.state.index.search(term).hits},{'essential-eight'})
        self.assertEqual({h.control.framework_key for h in self.state.index.search('ACSC strategies').hits},{'asd-strategies'})

    def test_workspace_scope_and_export_remove_overlap(self):
        c=next(c for c in workspace.CONTROLS if c['id']=='AP-01')
        both={'asd-strategies','essential-eight'}
        ids={m['uid'] for m in workspace.mappings(c,both)}
        self.assertNotIn('asd-strategies:s01',ids)
        self.assertIn('asd-strategies:s01',{m['uid'] for m in workspace.mappings(c,{'asd-strategies'})})
        page=workspace.render(self.state.corpus,{'control':['AP-01']})
        self.assertIn(families.ASD_LABEL,page)
        self.assertIn('View the broader ACSC strategy',page)
        exact=workspace.render(self.state.corpus,{'q':['asd-strategies:s01'],'control':['AP-01']})
        self.assertIn('q=asd-strategies%3As01',exact)
        rows=list(csv.DictReader(io.StringIO(workspace.export_csv({'q':['AP-01']}))))
        ids={row['Source UID'] for row in rows if row['Control']=='AP-01'}
        self.assertTrue(ids)
        self.assertEqual(ids,families.preferred_uids(ids))

    def test_user_qualifiers_removed_and_setup_not_repeated(self):
        page=workspace.render(self.state.corpus,{'control':['AD-01'],'assessment':['technical']})
        for phrase in ('An effective control does not automatically','different measures','publisher certification tests'):
            self.assertNotIn(phrase,page)
        self.assertEqual(page.count('Console setup and validation'),1)
        self.assertEqual(page.count('Live AD/M365/Azure behaviour'),1)
        self.assertIn('Before you start',page)
        self.assertIn('PowerShell commands',page)
        review=framework_review(self.state.corpus)
        self.assertEqual(review.count(families.ASD_LABEL),1)


if __name__=='__main__': unittest.main()
