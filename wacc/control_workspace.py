"""Control-centred library; publisher records remain unchanged."""
import csv
import html
import io
import json
from pathlib import Path
import re
from urllib.parse import urlencode

LIBRARY_DIR = Path(__file__).resolve().parents[1] / 'data/library'
CONTROLS = []
for library_file in sorted(LIBRARY_DIR.glob('*.json'), key=lambda p: (p.stem != 'privileged-access', p.name)):
    library = json.loads(library_file.read_text(encoding='utf-8'))
    CONTROLS.extend({**c, 'topic': library['topic']} for c in library['controls'])
# Related-control navigation works from either end of a reviewed connection.
_by_id = {c['id']: c for c in CONTROLS}
for _control in CONTROLS:
    for _related in list(_control['related']):
        if _related in _by_id and _control['id'] not in _by_id[_related]['related']:
            _by_id[_related]['related'].append(_control['id'])
TOPICS = list(dict.fromkeys(c['topic'] for c in CONTROLS))
FRAMEWORKS = sorted({m['uid'].split(':')[0] for c in CONTROLS for m in c['mappings']})


def scope(params):
    return set(params.get('fw', [])) & set(FRAMEWORKS) if 'scope' in params else set(FRAMEWORKS)


def mappings(control, selected):
    return [m for m in control['mappings'] if m['uid'].split(':')[0] in selected]


def matching(query, selected, topic=""):
    tokens = re.findall(r'\w+', query.lower())
    return [c for c in CONTROLS if (not topic or c["topic"] == topic) and mappings(c, selected) and all(t in
            (json.dumps({**c, 'mappings': mappings(c, selected)}, ensure_ascii=False)).lower() for t in tokens)]


def url(selected, control=None, query='', topic=''):
    pairs = [('scope','1')] + [('fw', f) for f in sorted(selected)]
    if topic:
        pairs.append(('topic', topic))
    if control:
        pairs.append(('control', control))
    if query:
        pairs.append(('q', query))
    return '/library?' + urlencode(pairs)


def export_csv(params):
    selected = scope(params)
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['Control','Title','Source UID','Relationship','Mapping provenance','Scope conditions'])
    for c in matching((params.get('q') or [''])[0], selected, (params.get('topic') or [''])[0]):
        for m in mappings(c, selected):
            writer.writerow([c['id'],c['title'],m['uid'],m['relationship'],m['provenance'],m['basis']])
    return out.getvalue()


STYLE = '''
:root{color-scheme:light dark;--bg:#f4f6f8;--paper:#fff;--ink:#172b40;--quiet:#586879;--line:#d9e1e8;--accent:#146d70;--soft:#e8f3f2}
@media(prefers-color-scheme:dark){:root{--bg:#101820;--paper:#17232e;--ink:#e3edf4;--quiet:#a9bbc9;--line:#324552;--accent:#7ccbc3;--soft:#203d3d}}
[hidden]{display:none!important}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 'Segoe UI',sans-serif}a{color:var(--accent)}header{padding:24px 32px;background:var(--paper);border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:20px}h1{font-size:25px;margin:0}h2{font-size:23px;margin:0 0 10px}h3{font-size:17px;margin:0 0 12px}p{margin:8px 0 16px}.muted,small{color:var(--quiet)}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}.workspace{display:grid;grid-template-columns:320px minmax(0,1fr);max-width:1500px;margin:auto;gap:24px;padding:24px}.sidebar,.box{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:18px}.sidebar{align-self:start;position:sticky;top:16px}.control-link{display:block;text-decoration:none;color:var(--ink);border-top:1px solid var(--line);padding:14px 10px;border-radius:6px}.control-link[aria-current=page]{background:var(--soft);border-left:3px solid var(--accent)}.control-link small{display:block}.controls{margin-top:18px;max-height:45vh;overflow-y:auto}input,select,textarea,button{font:inherit;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:6px;padding:9px}input:not([type=checkbox]),textarea,select{width:100%}textarea{min-height:100px;resize:vertical}button,.button{cursor:pointer;background:var(--accent);color:var(--paper);padding:9px 14px;border:0;text-decoration:none;border-radius:6px;display:inline-block}.filters label{display:block;margin:7px 0}.filters input{margin-right:8px}.filters fieldset{border:0;padding:10px 0;margin:0}.filters legend{font-weight:600}.risk{border-left:4px solid var(--accent);background:var(--soft);padding:14px 18px;border-radius:6px}.steps{display:grid;grid-template-columns:110px 1fr;gap:12px}.steps dt{font-weight:700}.steps dd{margin:0 0 8px}.record-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.record-grid label{display:block}.wide{grid-column:1/-1}.record-grid label span{display:block;font-weight:600;margin-bottom:5px}details{border-top:1px solid var(--line);padding:14px 0}summary{cursor:pointer}.badge{font-size:12px;background:var(--soft);padding:3px 7px;border-radius:4px;display:inline-block}.source-text{white-space:pre-wrap;font-size:14px}.actions{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-top:15px}nav{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}#save-state{font-size:13px}.empty{padding:28px}.pilot{max-width:1450px;margin:16px auto 0;padding:0 24px;font-size:13px;color:var(--quiet)}@media(max-width:850px){.workspace{grid-template-columns:1fr;padding:14px}.sidebar{position:static}.record-grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr}header{padding:18px;align-items:start;flex-direction:column}}
'''

SCRIPT = r'''
function validateRecord(data, id) {
 const fields=['owner','date','scope','applicability','result','evidence','findings','actions'];
 if(!data || data.version!==1 || !data.control || data.control.id!==id)
   throw new Error('Choose a version 1 assessment downloaded for '+id+'.');
 const a=data.assessment;
 if(!a || Array.isArray(a) || typeof a!=='object' || Object.keys(a).length!==fields.length ||
    fields.some(k=>!Object.prototype.hasOwnProperty.call(a,k) || typeof a[k]!=='string' || a[k].length>100000))
   throw new Error('The assessment fields are missing or invalid.');
 if(!['Not determined','Applicable','Not applicable'].includes(a.applicability) ||
    !['Not assessed','Effective','Partially effective','Ineffective'].includes(a.result) ||
    (a.date && !/^\d{4}-\d{2}-\d{2}$/.test(a.date)))
   throw new Error('The assessment status or date is invalid.');
 if(a.date && new Date(a.date+'T00:00:00Z').toISOString().slice(0,10)!==a.date)
   throw new Error('The assessment date is invalid.');
 return Object.fromEntries(fields.map(k=>[k,a[k]]));
}
(function(){
 function updateStatuses(){
 document.querySelectorAll('[data-record-id]').forEach(node=>{
  try{const a=JSON.parse(localStorage.getItem('wacc-control-assessment-v1:'+node.dataset.recordId)||'null');
   node.textContent=a ? (a.applicability==='Not applicable' ? 'Not applicable' : a.result || 'Not assessed') : 'Not assessed';
  }catch(e){node.textContent='Record unavailable';}
 });
 }
 updateStatuses();
 const form=document.getElementById('assessment-record');
 if(!form)return;
 const context=JSON.parse(document.getElementById('control-context').textContent);
 const key='wacc-control-assessment-v1:'+context.id;
 const state=document.getElementById('save-state');
 let dirty=false;
 window.addEventListener('beforeunload', e=>{if(dirty){e.preventDefault();e.returnValue='';}});
 function readForm(){const result={}; new FormData(form).forEach((v,k)=>result[k]=v);return result;}
 try{const stored=localStorage.getItem(key);if(stored){const data=JSON.parse(stored);Object.keys(data).forEach(k=>{if(form.elements.namedItem(k))form.elements.namedItem(k).value=data[k];});state.textContent='Saved record loaded from this browser.';}}
 catch(e){state.textContent='Browser storage is unavailable. Download the record to keep it.';}
 form.addEventListener('submit',e=>{e.preventDefault();try{localStorage.setItem(key,JSON.stringify(readForm()));dirty=false;state.textContent='Saved in this browser.';updateStatuses();}catch(e){state.textContent='Could not save. Download the record to keep it.';}});
 form.addEventListener('input',event=>{if(!event.target.name)return;dirty=true;state.textContent='Unsaved changes';});
 const picker=document.getElementById('restore-file'), preview=document.getElementById('restore-preview'), apply=document.getElementById('apply-restore');
 let pending=null;
 document.getElementById('choose-record').addEventListener('click',()=>{picker.value='';pending=null;apply.hidden=true;picker.click();});
 picker.addEventListener('change',async()=>{
  pending=null;apply.hidden=true;
  const file=picker.files[0];if(!file)return;
  try{if(file.size>2000000)throw new Error('Choose an assessment file smaller than 2 MB.');
   pending=validateRecord(JSON.parse(await file.text()),context.id);
   preview.textContent='Ready to restore '+context.id+' ('+pending.result+'). This replaces the current record, including unsaved changes.';
   apply.hidden=false;
  }catch(e){preview.textContent=e.message;}
 });
 apply.addEventListener('click',()=>{
  if(!pending)return;
  Object.keys(pending).forEach(k=>form.elements.namedItem(k).value=pending[k]);
  dirty=true;form.requestSubmit();pending=null;apply.hidden=true;preview.textContent='';
 });
 document.getElementById('download-record').addEventListener('click',()=>{
 const blob=new Blob([JSON.stringify({version:1,exported_at:new Date().toISOString(),control:context,assessment:readForm()},null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=context.id+'-assessment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 });
})();
'''


def render(corpus, params):
    esc = html.escape
    selected = scope(params)
    query = (params.get('q') or [''])[0]
    topic = (params.get('topic') or [''])[0]
    found = matching(query, selected, topic)
    requested = (params.get('control') or [''])[0]
    chosen = next((c for c in CONTROLS if c['id'] == requested), None) if requested else (found[0] if found else None)
    source_url = '/?' + urlencode({'q': query or (chosen['topic'] if chosen else topic)})
    checkboxes=''.join('<label><input type="checkbox" name="fw" value="%s"%s>%s</label>' %
                      (esc(f),' checked' if f in selected else '',esc(corpus.frameworks[f].short_name if f in corpus.frameworks else f)) for f in FRAMEWORKS)
    listing=''.join('<a class="control-link" href="%s"%s><small>%s</small><strong>%s</strong><small>%d source references</small><small class="record-status" data-record-id="%s">Not assessed</small></a>' %
                    (esc(url(selected,c['id'],query,topic)), ' aria-current="page"' if chosen and chosen['id']==c['id'] else '',c['id'],esc(c['title']),len(mappings(c,selected)),c['id']) for c in found)
    topic_options = '<option value="">All topics</option>' + ''.join('<option%s>%s</option>' % (' selected' if t==topic else '',esc(t)) for t in TOPICS)
    sidebar='<aside class="sidebar"><form class="filters" action="/library"><label for="library-q">Find a control</label><input id="library-q" type="search" name="q" value="%s" placeholder="A subject or source identifier"><label for="topic">Topic</label><select id="topic" name="topic">%s</select><input type="hidden" name="scope" value="1"><fieldset><legend>Framework scope</legend>%s</fieldset><button>Apply scope and search</button></form><div class="controls"><small>%d controls in scope</small>%s</div><p class="muted">%s</p><a href="%s">Export scoped mappings (CSV)</a></aside>' % (esc(query),topic_options,checkboxes,len(found),listing,'' if found else 'No controls match this scope and search.',esc(url(selected,query=query,topic=topic).replace('/library?','/library/export.csv?')))
    main='<section class="box empty"><h2>No control selected</h2><p>Choose frameworks and a control from the list, or search the full source corpus.</p><a href="/?q=%s">Search source corpus</a></section>' % esc(query or 'privileged access')
    if chosen:
        c=chosen
        refs=mappings(c,selected)
        rows=[]
        for m in refs:
            source=corpus.control(m['uid'])
            label=('%s %s' % (corpus.frameworks[source.framework_key].short_name,source.identifier)) if source else m['uid']
            body='<p class="source-text">%s</p>' % esc(source.text) if source else '<p>Source text is not loaded in this build. This reference cannot be assessed here.</p>'
            if source:
                body+='<p><a href="/?%s">Open source control, assessment methods and linked controls →</a></p>' % esc(urlencode({'q':source.uid,'view':'cards'}))
                statements=[s for s in corpus.statements_for(source.uid) if s.is_published]
                if statements:
                    body+='<details><summary>Published assessment material (%d)</summary>%s</details>' % (len(statements),''.join('<p><strong>%s</strong></p><p class="source-text">%s</p>'%(esc(s.published_by),esc(s.text)) for s in statements))
            rows.append('<details><summary><strong>%s</strong> <span class="badge">%s</span></summary><p>%s</p><small>%s</small>%s</details>'%(esc(label),esc(m['relationship']),esc(m['basis']),esc(m['provenance']),body))
        related=' · '.join('<a href="%s">%s — %s</a>'%(esc(url(selected,uid)),uid,esc(next(x['title'] for x in CONTROLS if x['id']==uid))) for uid in c['related'])
        context={**c,'mappings':refs,'selected_frameworks':sorted(selected)}
        main='''<article><section class="box"><div class="eyebrow">%s · %s</div><h2>%s</h2><p>%s</p><p class="muted"><strong>Scope:</strong> %s</p>%s<div class="risk"><strong>Business risk</strong><br>%s</div><nav><a href="#assessment">Assessment</a><a href="#record">Evidence and result</a><a href="#sources">Source requirements</a></nav></section>
<section class="box" id="assessment"><h3>Assess this control</h3><dl class="steps"><dt>Examine</dt><dd>%s</dd><dt>Interview</dt><dd>%s</dd><dt>Test</dt><dd>%s</dd><dt>Expected result</dt><dd>%s</dd></dl><small>Suggested assessment for this control. Check the source-specific conditions below.</small></section>
<section class="box" id="record"><h3>Evidence and result</h3><p class="muted">One record per control, saved in this browser. Download a copy for backup or restore a previously downloaded record.</p><form id="assessment-record"><div class="record-grid"><label><span>Control owner</span><input name="owner"></label><label><span>Assessment date</span><input type="date" name="date"></label><label class="wide"><span>Systems and assessment scope</span><textarea name="scope"></textarea></label><label><span>Applicability</span><select name="applicability"><option>Not determined</option><option>Applicable</option><option>Not applicable</option></select></label><label><span>Result</span><select name="result"><option>Not assessed</option><option>Effective</option><option>Partially effective</option><option>Ineffective</option></select></label><label class="wide"><span>Evidence references and sample</span><textarea name="evidence"></textarea></label><label class="wide"><span>Findings, exceptions and applicability rationale</span><textarea name="findings"></textarea></label><label class="wide"><span>Actions, responsible person and due date</span><textarea name="actions"></textarea></label></div><div class="actions"><button type="submit">Save assessment</button><button type="button" id="download-record">Download assessment</button><button type="button" id="choose-record">Restore assessment</button><input id="restore-file" type="file" accept="application/json,.json" hidden><span id="restore-preview" role="status"></span><button id="apply-restore" type="button" hidden>Confirm restore</button><span id="save-state" role="status">Not saved yet</span></div></form></section>
<section class="box" id="sources"><h3>Source requirements · %d references in scope</h3><p class="muted">These locally reviewed connections describe overlap, not compliance. An effective control does not automatically satisfy every linked requirement.</p>%s</section><section class="box"><h3>Related controls</h3><p>%s</p></section></article><script type="application/json" id="control-context">%s</script>''' % (
            c['id'],esc(c['topic']),esc(c['title']),esc(c['statement']),esc(c['scope']),'<p class="muted">This control has no references in the selected framework scope.</p>' if not refs else '',esc(c['risk']),esc(c['examine']),esc(c['interview']),esc(c['test']),esc(c['expected']),len(refs),''.join(rows) or '<p>No source references selected.</p>',related,json.dumps(context,ensure_ascii=False).replace('<','\\u003c'))
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WACC · Control workspace</title><style>%s</style></head><body><header><div><div class="eyebrow">WA Control Crosswalk</div><h1>Control workspace</h1></div><a href="%s">Browse source corpus →</a></header><p class="pilot">Control library · %d controls across %d topics, with reviewed source connections. The full corpus remains available in the source browser.</p><div class="workspace">%s<main>%s</main></div><script>%s</script></body></html>' % (STYLE,esc(source_url),len(CONTROLS),len(TOPICS),sidebar,main,SCRIPT)
