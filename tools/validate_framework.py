"""Preview a manually prepared OSCAL catalog before registering it in WACC."""
import argparse
import json
import re
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wacc.loaders import oscal
from wacc.model import Corpus, Framework, Fidelity, Jurisdiction, Licence, Level, Tier


def validate(path, key, expected=None, publisher=None):
    if not re.fullmatch(r'[a-z][a-z0-9-]*',key):
        raise ValueError('Framework key must use lowercase letters, numbers and hyphens')
    corpus=Corpus()
    framework=Framework(key=key,name=key,short_name=key,publisher=publisher or 'Local preview',
        jurisdiction=Jurisdiction.INTERNATIONAL,tier=Tier.CATALOGUE,
        fidelity=Fidelity.CURATED_EXTRACT,licence=Licence.IMPORT_ONLY,
        source_file=Path(path).name,levels=[Level('control','Control',0,assessable=True)])
    corpus.add_framework(framework)
    counts=oscal.load_into(corpus,framework,str(path),assessment_publisher=publisher)
    problems=list(corpus.check())+list(corpus.load_warnings)
    if not corpus.controls: problems.append('No controls found in catalog')
    for c in corpus.controls.values():
        if not c.identifier.strip(): problems.append('Missing control identifier')
        if not c.text.strip(): problems.append('Missing statement text: '+c.uid)
    if expected is not None and len(corpus.controls)!=expected:
        problems.append('Expected %d controls; loaded %d'%(expected,len(corpus.controls)))
    return dict(counts=counts,uids=list(corpus.controls),problems=problems)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path',type=Path)
    parser.add_argument('--key',required=True)
    parser.add_argument('--expect-controls',type=int)
    parser.add_argument('--assessment-publisher')
    args=parser.parse_args()
    try: result=validate(args.path,args.key,args.expect_controls,args.assessment_publisher)
    except (ValueError,KeyError,TypeError,OSError) as error:
        print(json.dumps({'problems':[str(error)]},indent=2)); return 1
    print(json.dumps(result,indent=2))
    return bool(result['problems'])


if __name__=='__main__': sys.exit(main())
