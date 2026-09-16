"""Cross-check authored command parameters against cached Microsoft references.

This checks parameter spelling, not service execution or parameter-set semantics.
Run review_assessment_sources.py and validate_assessment_commands.ps1 first.
"""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def check():
    sources=json.loads((ROOT/'data/assessment-sources.json').read_text(encoding='utf-8'))
    docs={s['title'].removeprefix('Microsoft: ').lower():key for key,s in sources.items()}
    parsed=json.loads((ROOT/'data/review/commands-ps51.json').read_text(encoding='utf-8-sig'))
    problems=[]; checked=set()
    common={'ErrorAction','WarningAction','InformationAction','Verbose','Debug','ErrorVariable','OutVariable','OutBuffer','PipelineVariable'}
    for row in parsed:
        for call in row['commands']:
            name=call['name'] or ''
            if name.lower() not in docs: continue
            key=docs[name.lower()]
            text=(ROOT/'data/review/assessment-sources'/(key+'.txt')).read_text(encoding='utf-8')
            checked.add(name)
            for parameter in call['parameters']:
                if parameter not in common and not re.search(r'-'+re.escape(parameter)+r'\b',text,re.I):
                    problems.append((row['id'],name,parameter))
    print(json.dumps({'documented_commands_checked':len(checked),'unmatched_parameters':problems},indent=2))
    return problems


if __name__=='__main__': raise SystemExit(bool(check()))
