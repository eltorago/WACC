"""Generate the versioned public JSON contracts from shared schema definitions."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from wacc.policy.contracts import AUTOMATED
from wacc.policy.rules import PATTERNS


def obj(properties, required=None, extra=False):
    return dict(type='object',properties=properties,required=list(properties) if required is None else required,additionalProperties=extra)


def array(items,maximum=20000):
    return dict(type='array',items=items,maxItems=maximum)


def ref(name):return {'$ref':'#/$defs/'+name}


def generate():
    string={'type':'string','maxLength':2000000}
    strings=array(string)
    number={'type':'number'}
    boolean={'type':'boolean'}
    nullable={'type':['string','null']}
    defs={}
    defs['locator']=obj({k:({'type':['integer','null']} if k in ('start','end','line','paragraph','table','row','cell','page') else nullable) for k in ('kind','start','end','line','heading','paragraph','table','row','cell','page','boundingBox','section','reference')},required=[])
    defs['rule']={'oneOf':[obj({'all':dict(type='array',items=ref('rule'),minItems=1,maxItems=16)}),
                           obj({'any':dict(type='array',items=ref('rule'),minItems=1,maxItems=16)}),
                           obj({'phrases':dict(type='array',items={'type':'string','minLength':1,'maxLength':150},minItems=1,maxItems=32)}),
                           obj({'pattern':{'enum':list(PATTERNS)}})]}
    defs['atom']=obj(dict(id=string,interpretation=string,rule={'anyOf':[{'type':'null'},ref('rule')]},mandatory=boolean,
                         ruleVersion=string,assessmentMethod=string,reviewStatus={'enum':['DraftNeedsHumanReview','ManualReviewOnly','HumanApproved']},provenance=string))
    defs['span']=obj(dict(start={'type':'integer','minimum':0},end={'type':'integer','minimum':1},normalisedStart={'type':'integer'},normalisedEnd={'type':'integer'},signal=string))
    defs['evidence']=obj(dict(id=string,documentId=string,documentHash=string,passageId=string,obligationId=string,requirementId=string,
                             excerpt=string,locator=ref('locator'),matchedSpans=array(ref('span')),
                             checks=array(obj(dict(operator={'enum':['phrases','pattern']},condition={'type':['string','array']},passed=boolean))),
                             ruleVersion=string,corpusVersion=string,state={'enum':['Matched','Ambiguous','Contradiction']},relation={'const':'Direct'},
                             matchStrength={'enum':['Strong','Moderate','Weak','Unknown']},context={'const':'same_sentence'},limitations=strings))
    base=dict(id=string,frameworkId=string,officialReference=string,heading=string,parentId=nullable,authoritativeText=string,
              context=string,sourceLocator=ref('locator'),obligations=array(ref('atom'),50))
    defs['requirement']=obj(base)
    defs['finding']=obj(dict(**base,automatedFinding={'enum':list(AUTOMATED)},applicability={'enum':['InScope','NotApplicable','Undetermined']},
                            reviewState={'enum':['Pending','Reviewed','NeedsReReview']},reviewerFinding=nullable,
                            atomResults=array(obj(dict(id=string,state={'enum':['NotAssessed','Conflict','Ambiguous','Matched','Missing']}))),
                            evidence=array(ref('evidence')),flags=strings,candidateProportion={'type':['number','null'],'minimum':0,'maximum':1},missingObligations=strings))
    defs['passage']=obj(dict(id=string,text=string,locator=ref('locator')))
    document=dict(id=string,sha256=string,name=string,path=string,format=string,status={'enum':['Ready','Incomplete','Failed']},
                  approvalStatus={'enum':['approved','draft','unknown','superseded']},effectiveDate=nullable,included=boolean,
                  warnings=strings,passages=array(ref('passage'),100000),parserVersion=string,retention={'enum':['evidence','extracted']},extractedPassageCount={'type':'integer'})
    defs['document']=obj(document,required=[k for k in document if k not in ('effectiveDate','extractedPassageCount')])
    defs['framework']=obj(dict(id=string,title=string,edition=string,sourceFile=nullable,extractHash=string,sourceUri=nullable,licence=string,sourceHash=nullable),required=['id','title','edition','extractHash'])
    defs['versions']=obj(dict(engine=string,corpus=string,frameworks=array(ref('framework'),100),rulesHash=string,normaliser=string,retrieval=string,parser=string))
    defs['scope']=obj(dict(description=string,mode={'enum':['SingleDocument','PolicySet']},selectedDocumentIds=strings,
                          duplicates=array(obj(dict(path=string,documentId=string)),250),retention={'enum':['evidence','extracted']}))
    defs['mapping']=obj(dict(source=string,target=string,relationship=string,relation={'const':'MappedOnly'},provenance=string,reviewStatus=string))
    defs['review']=obj(dict(id=string,runId=string,requirementId=string,finding={'enum':['Covered','PartiallyCovered','NotCovered','NotAssessed','NotApplicable']},
                           reason=string,reviewer=string,identitySource=string,timestamp=string,confirmedObligations=strings,selectedEvidence=strings,comment=string,
                           manualEvidence=array(obj(dict(id=string,documentId=string,documentHash=string,passageId=string,obligationId=string,excerpt=string,locator=ref('locator'),relation={'const':'Direct'},provenance=string)))))
    defs['reviewedFinding']=obj(dict(**defs['finding']['properties'],review=ref('review')),required=defs['finding']['required'])
    run=obj(dict(schemaVersion={'const':'1.0'},runId=string,createdAt=string,name=string,organisation=string,
                 scope=ref('scope'),versions=ref('versions'),documents=array(ref('document'),250),requirements=array(ref('finding')),
                 mappings=array(ref('mapping'),100000),limitations=strings,canonicalHash=string))
    corpus=obj(dict(version=string,frameworks=array(ref('framework'),100),requirements=array(ref('requirement')),mappings=array(ref('mapping'),100000),rulesHash=string,status=string))
    cli=obj(dict(schemaVersion={'const':'1.0'},operation=string,status={'enum':['Completed','CompletedWithLimitations','Cancelled','Failed']},warnings=strings,errors=strings,
                 assessmentPath=nullable,analysisRunId=string,scope=ref('scope'),versions=ref('versions'),summary={'type':'object'},requirements=array(ref('reviewedFinding')),documents=array(ref('document'),250)),
            required=['schemaVersion','operation','status','warnings','errors'],extra=True)
    folder=ROOT/'schemas/policy';folder.mkdir(parents=True,exist_ok=True)
    for name,schema in [('run',run),('corpus',corpus),('cli',cli)]:
        schema.update({'$schema':'https://json-schema.org/draft/2020-12/schema','$id':'https://wacc.local/schemas/policy/'+name+'/1.0','$defs':defs})
        (folder/(name+'.schema.json')).write_text(json.dumps(schema,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':generate()
