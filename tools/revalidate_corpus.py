"""Recheck source integrity and identify candidates for more practical controls."""
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wacc.build import build
from wacc.control_workspace import CONTROLS
from wacc.workspace_technical import CHECKS
from wacc.wa_audit_context import REPORTS
from wacc.packaging import check
from wacc.sources import load_catalogue

CANDIDATES=[
    ('Email authentication and message protection','High','UH-01 UH-02 DP-03',
     'scuba:ms.exo.2.2v3 scuba:ms.exo.3.1v1 scuba:ms.exo.4.1v1 scuba:ms.securitysuite.2.3v1',
     r'\b(?:smtp|dmarc|dkim|spf|email security|email authentication|mail protection)\b',
     'Create a dedicated workspace topic and control covering domain authentication, impersonation, attachment/link protection and mail-flow exceptions. Technical checks exist, but they currently sit beneath broad application-hardening controls.'),
    ('Application identities and consent','High','IA-02 IA-03 SD-01',
     'scuba:ms.aad.5.2v1 scuba:ms.aad.5.3v1 mcsb:im-3',
     r'\b(?:service principals?|application identities|oauth|managed identities|application permissions)\b',
     'Add a dedicated control for non-human identity ownership, permissions, consent, credentials and retirement. Existing identity controls cover parts of the lifecycle; users need a direct route to these cloud-specific checks.'),
    ('External collaboration and guest access','High','IA-01 IA-02 DP-03 SC-03',
     'scuba:ms.aad.8.2v1 scuba:ms.sharepoint.1.1v1 scuba:ms.teams.2.1v2',
     r'\b(?:guest users?|external sharing|external collaboration|cross.tenant|federation)\b',
     'Add a control joining guest sponsorship, cross-tenant trust, sharing links and collaboration expiry. Coverage is currently divided between access, data protection and supplier controls.'),
    ('Low-code applications and public analytics','High','SD-01 DP-03 PI-02',
     'scuba:ms.powerplatform.2.1v1 scuba:ms.powerplatform.3.1v1 scuba:ms.powerbi.1.1v1',
     r'\b(?:power platform|power bi|power pages|low.code|connectors|publish to web)\b',
     'Create a control for environment ownership, connector boundaries and public publication. This is a distinct business-managed application path, with technical assessment coverage now available.'),
    ('Business application authorisation and data integrity','High','IA-02 SD-03 PI-02',
     'mcsb:pa-7 mcsb:ds-5',
     r'\b(?:segregation of duties|transaction integrity|data integrity|input validation|authori[sz]ation)\b',
     'Add a control for transaction limits, conflicting duties, record-level access and verified data changes. The State Government 2025 and Assist audits provide specific WA examples; configuration and software-testing controls alone do not express this business outcome.'),
    ('Cloud tenant and subscription governance','Medium','AM-01 AM-02 GV-01 SC-02',
     'mcsb:am-2 mcsb:gs-11 mcsb:pv-2',
     r'\b(?:multi.cloud|multi.tenant|cloud services|cloud service|subscription|shared responsibility)\b',
     'Consider a dedicated control joining tenant ownership, approved subscriptions/services, shared responsibility and drift monitoring. Existing controls and the new baseline assessment provide substantial partial coverage.'),
    ('AI agent and assistant access','Medium','IA-02 DP-03 SD-02',
     'scuba:ms.aad.9.1v1 mcsb:im-3',
     r'\b(?:ai agents?|artificial intelligence|copilot|autonomous technologies)\b',
     'Review a separate control for agent identity, accessible data, consent and risky-agent response. The corpus contains a current SCuBA risky-agent policy, but the older MCSB v1 edition is not an AI security baseline. Further publisher-specific review is needed before creating broad AI claims.'),
]


def main():
    corpus,report=build(False)
    problems=list(corpus.check())
    problems.extend(v.describe() for v in check(str(ROOT)))
    load_catalogue()
    for link in corpus.links:
        if not corpus.control(link.source_uid) or not corpus.control(link.target_uid):
            problems.append('Unresolved corpus link: '+link.source_uid+' -> '+link.target_uid)
    for control in CONTROLS:
        for mapping in control['mappings']:
            if 'uid' in mapping and not corpus.control(mapping['uid']):
                problems.append('Unresolved workspace mapping: '+mapping['uid'])
    parents={c['id'] for c in CONTROLS}
    if parents!={p for c in CHECKS for p in c['parents']}:
        problems.append('Technical-check parent coverage mismatch')
    candidates=[]
    for title,priority,existing,uids,pattern,reason in CANDIDATES:
        counts=Counter(c.framework_key for c in corpus.controls.values() if re.search(pattern,(c.title or '')+' '+c.text,re.I))
        for uid in uids.split():
            if not corpus.control(uid): problems.append('Candidate reference missing: '+uid)
        candidates.append(dict(title=title,priority=priority,existing_controls=existing.split(),source_uids=uids.split(),
                               mention_counts_by_framework=dict(sorted(counts.items())),reason=reason))
    data=dict(reviewed_on=date.today().isoformat(),records=len(corpus.controls),frameworks=len(report.loaded),
              framework_counts={f.key:len(corpus.controls_for(f.key)) for f in corpus.ordered_frameworks()},
              workspace_controls=len(CONTROLS),technical_checks=len(CHECKS),oag_reports=len(REPORTS),
              published_and_local_links=len(corpus.links),problems=problems,load_warnings=corpus.load_warnings,candidates=candidates)
    (ROOT/'data/validation/corpus-revalidation.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    lines=['# Corpus revalidation and additional control candidates','',
           'Review date: '+data['reviewed_on'], '',
           '%s source records across %d loaded frameworks; %d practical controls, %d technical checks and %d dated OAG reports.'%(format(data['records'],','),data['frameworks'],len(CONTROLS),len(CHECKS),len(REPORTS)),
           '', '## Integrity checks','',
           'Checked local publisher hashes, acquisition catalogue consistency, corpus structure, every corpus link, every workspace source reference and technical-check coverage for all practical controls.',
           '', 'Blocking integrity problems: %d.'%len(problems)]
    lines += ['- '+p for p in problems]
    lines += ['', '## Recommended additional controls','',
              'These are candidates for distinct practical controls or topics, not claims that the subjects are entirely absent. Related technical checks already exist in this change. Priority reflects distinct scope and WA/cloud relevance, not a frequency-derived risk score. No new practical control has been created automatically from a text match.',
              '', '| Candidate | Priority | Current partial coverage | Why add it |','|---|---|---|---|']
    for x in candidates:
        lines.append('| %s | %s | %s | %s |'%(x['title'],x['priority'],', '.join(x['existing_controls']),x['reason']))
    lines += ['', '## How frequency was used','',
              'The JSON companion records distinct source records matching each declared topic expression, broken down by framework. It counts neither independent organisations nor unique obligations: parent records, repeated maturity requirements and SCF mappings can repeat concepts. SCF volume is therefore not allowed to determine priority on its own. Specific source UIDs support each candidate.',
              '', '## Remaining source limitations','']
    lines += ['- '+warning for warning in corpus.load_warnings]
    lines += ['', 'The warnings above include existing retired/mismatched references and unavailable local CIS benchmark extracts. They are retained visibly rather than converted into invented mappings. The Essential Eight legislation reference needs a separate edition/incorporation review. SCF’s generic NIST R5 mapping has not been transferred to NIST 5.2.0.',
              '', 'Reproduce with `python tools/revalidate_corpus.py`. Run `python tests/run_all.py` for behavioural regression checks.', '']
    (ROOT/'docs/corpus-revalidation.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:data[k] for k in ('records','frameworks','workspace_controls','technical_checks','oag_reports','problems')},indent=2))
    return bool(problems)


if __name__=='__main__': sys.exit(main())
