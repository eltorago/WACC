"""Measure topic prevalence in assessable corpus entries without ranking by search score."""
import json
from pathlib import Path
import re
import sys
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wacc.serve import State
from wacc.archetypes import classify

PATTERNS={
 'Risk and governance':r'\b(risk (?:assessment|management|register|tolerance|appetite)|assess\w* risks?|governance|security (?:polic(?:y|ies)|strategy)|accountab\w*|security roles|security responsibilities)\b',
 'Identity and access management':r'\b(access control|access (?:rights|privileges|permissions|authori[sz]ations)|accounts?|authenticat\w*|credentials?|identities|identity|least privilege|passwords?)\b',
 'Incident management':r'\b(incidents?|incident response|incident handling|incident reporting)\b',
 'Asset management':r'\b(asset (?:inventory|inventories|management|register)|inventor\w*|assets? (?:are|is) identified|hardware assets?|software assets?)\b',
 'Data protection':r'\b(data (?:classif\w*|protect\w*|retention|loss|handling)|information (?:classif\w*|handling)|sensitive (?:data|information)|personally identifiable|privacy)\b',
 'Network security':r'\b(network (?:segmentation|security|boundar\w*)|firewalls?|gateways?|boundary protection|remote access|network traffic|wireless)\b',
 'Cryptography':r'\b(cryptograph\w*|encrypt\w*|cipher\w*|cryptographic keys?|key management)\b',
 'Supply chain':r'\b(supply chain|suppliers?|third.part(?:y|ies)|service providers?|outsourc\w*|vendors?)\b',
 'Secure configuration':r'\b(configuration (?:settings?|management|baselines?|changes?|standards?)|harden\w*|least functionality|default settings?|unnecessary (?:services|ports))\b',
 'Security monitoring':r'\b(logs?|logging|audit records?|security monitoring|intrusion detection|continuous monitoring)\b',
 'Vulnerability management':r'\b(vulnerabilit\w*|patch\w*|security updates?|unsupported software)\b',
 'Backup and recovery':r'\b(backups?|backed up|restor\w*|disaster recovery|recovery (?:time|point|plans?))\b',
 'Security awareness':r'\b(training|awareness|security education|security literacy)\b',
 'Physical security':r'\b(physical (?:access|security|protection)|visitors?|secure areas?|perimeter|facility access)\b',
 'Secure development':r'\b(software development|development (?:life.?cycle|environment)|secure (?:coding|development)|source code|application security|code review)\b',
 'Media handling':r'\b(saniti[sz]\w*|media (?:disposal|storage|transport|protection)|removable media|degauss\w*)\b',
 'Business continuity':r'\b(business continuity|contingency (?:plans?|planning)|continuity (?:plans?|planning)|resilien\w*)\b',
}

def measure(state):
    eligible=[]
    seen=set()
    for c in state.corpus.controls.values():
        if classify(c,state.relations.ancestors(c.uid))[2] is not None:continue
        text=state.relations.quotable_text(c.uid)
        if c.title and not c.title_is_shared:text=c.title+' '+text
        key=(c.framework_key,' '.join(text.casefold().split()))
        if key in seen:continue
        seen.add(key);eligible.append((c,text))
    totals=Counter(c.framework_key for c,_ in eligible)
    ranked=[]
    for topic,pattern in PATTERNS.items():
        hits=[c for c,t in eligible if re.search(pattern,t,re.I)]
        counts=Counter(c.framework_key for c in hits)
        ranked.append(dict(topic=topic,controls=len(hits),frameworks=len(counts),
            mean_framework_share=round(sum(counts[f]/totals[f] for f in totals)/len(totals)*100,2),
            per_framework=dict(sorted(counts.items())),sample_uids=[c.uid for c in hits[:8]]))
    ranked.sort(key=lambda r:(-r['controls'],-r['frameworks'],r['topic']))
    return dict(method='Explicit topic-pattern matches on assessable entries; duplicate text within each framework counted once. Topics overlap. Counts measure mentions, not importance or compliance. Mean framework share gives each loaded framework equal weight. Only loaded corpus content is counted.',patterns=PATTERNS,loaded_controls=len(state.corpus.controls),eligible_entries=len(eligible),eligible_frameworks=len(totals),topics=ranked)

if __name__=='__main__':
    report=measure(State())
    target=Path(__file__).resolve().parents[1]/'data/validation/topic_prevalence.json'
    target.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print('Eligible:',report['eligible_entries'],'frameworks:',report['eligible_frameworks'])
    for r in report['topics']:print(r['topic'],r['controls'],r['frameworks'],r['mean_framework_share'])
