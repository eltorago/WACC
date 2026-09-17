"""Load and display WACC's practical controls and their source connections."""
import csv
import html
import io
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from . import workspace_attack, workspace_technical, workspace_grc, wa_audit_context, publisher_guidance
from . import framework_families as families

LIBRARY_DIR = Path(__file__).resolve().parents[1] / 'data/library'
CONTROLS = []
for library_file in sorted(LIBRARY_DIR.glob('*.json')):
    library = json.loads(library_file.read_text(encoding='utf-8'))
    CONTROLS.extend({**c, 'topic': library['topic']} for c in library['controls'])
CONTROLS.sort(key=lambda c:(c['title'].casefold(),c['id']))
_extra_mappings=json.loads((LIBRARY_DIR.parent/'workspace-frameworks.json').read_text(encoding='utf-8'))
for _control in CONTROLS:
    _existing={m.get('uid') for m in _control['mappings']}
    for _mapping in workspace_technical.source_mappings(_control['id'])+_extra_mappings.get(_control['id'],[]):
        if _mapping['uid'] not in _existing:
            _control['mappings'].append(_mapping)
            _existing.add(_mapping['uid'])
# Related-control navigation works from either end of a reviewed connection.
_by_id = {c['id']: c for c in CONTROLS}
for _control in CONTROLS:
    for _related in list(_control['related']):
        if _related in _by_id and _control['id'] not in _by_id[_related]['related']:
            _by_id[_related]['related'].append(_control['id'])
TOPICS = sorted({c['topic'] for c in CONTROLS},key=str.casefold)
def mapping_source_key(mapping):
    """Return the scope key for either a control or a named guidance document."""
    return mapping['uid'].split(':')[0] if 'uid' in mapping else 'guidance'


FRAMEWORKS = sorted({mapping_source_key(m) for c in CONTROLS for m in c['mappings']})


def scope(params):
    return set(params.get('fw', [])) & set(FRAMEWORKS) if 'scope' in params else set(FRAMEWORKS)


def mappings(control, selected, deduplicate=True):
    refs = [m for m in control['mappings'] if mapping_source_key(m) in selected]
    keep = families.preferred_uids(m.get('uid') for m in refs if 'uid' in m) if deduplicate else None
    return [m for m in refs if keep is None or 'uid' not in m or m['uid'] in keep]


def matching(query, selected, topic="", corpus=None):
    identifiers = re.findall(r'\b[tm]\d{4}(?:\.\d{3})?\b', query, re.I)
    tokens = re.findall(r'\w+', re.sub(r'\b[tm]\d{4}(?:\.\d{3})?\b', '', query, flags=re.I).lower())
    found = []
    for c in CONTROLS:
        refs = mappings(c, selected, deduplicate=False)
        if (topic and c['topic'] != topic) or not refs:
            continue
        if not workspace_attack.matches_identifiers(c['id'], identifiers):
            continue
        text = (json.dumps({**c, 'mappings': refs}, ensure_ascii=False) + ' ' +
                workspace_attack.search_text(c['id'], corpus)+' '+workspace_technical.search_text(c['id'])).lower()
        if all(token in text for token in tokens):
            found.append(c)
    return found


def url(selected, control=None, query='', topic='', assessment='grc'):
    pairs = [('scope','1')] + [('fw', f) for f in sorted(selected)]
    if assessment == 'technical':
        pairs.append(('assessment','technical'))
    if topic:
        pairs.append(('topic', topic))
    if control:
        pairs.append(('control', control))
    if query:
        pairs.append(('q', query))
    return '/library?' + urlencode(pairs)


def export_csv(params, corpus=None):
    selected = scope(params)
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['Control','Title','Source UID','Relationship','Mapping provenance','Scope conditions'])
    for c in matching((params.get('q') or [''])[0], selected, (params.get('topic') or [''])[0], corpus):
        for m in mappings(c, selected):
            source_uid = m['uid'] if 'uid' in m else 'guidance:'+m['guidance']
            writer.writerow([c['id'],c['title'],source_uid,m['relationship'],m['provenance'],m['basis']])
    return out.getvalue()


STYLE = '''
.technical-check h4{margin:16px 0 6px}.technical-check li{margin:8px 0}.technical-check pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--bg);padding:14px;border-radius:6px;font-size:13px}.assessment-tabs a{padding:8px 14px;border:1px solid var(--line);border-radius:6px;text-decoration:none}.assessment-tabs a[aria-current=true]{background:var(--soft);border-color:var(--accent);font-weight:700}
.attack-connection{border-top:1px solid var(--line);padding:16px 0 4px}.attack-connection h4{font-size:16px;margin:0 0 8px}
:root{color-scheme:light dark;--bg:#f4f6f8;--paper:#fff;--ink:#172b40;--quiet:#586879;--line:#d9e1e8;--accent:#146d70;--soft:#e8f3f2}
@media(prefers-color-scheme:dark){:root{--bg:#101820;--paper:#17232e;--ink:#e3edf4;--quiet:#a9bbc9;--line:#324552;--accent:#7ccbc3;--soft:#203d3d}}
[hidden]{display:none!important}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 'Segoe UI',sans-serif}a{color:var(--accent)}header{padding:24px 32px;background:var(--paper);border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:20px}h1{font-size:25px;margin:0}h2{font-size:23px;margin:0 0 10px}h3{font-size:17px;margin:0 0 12px}p{margin:8px 0 16px}.muted,small{color:var(--quiet)}.eyebrow{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}.workspace{display:grid;grid-template-columns:320px minmax(0,1fr);max-width:1500px;margin:auto;gap:24px;padding:24px}.sidebar,.box{background:var(--paper);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:18px}.sidebar{align-self:start;position:sticky;top:16px}.control-link{display:block;text-decoration:none;color:var(--ink);border-top:1px solid var(--line);padding:14px 10px;border-radius:6px}.control-link[aria-current=page]{background:var(--soft);border-left:3px solid var(--accent)}.control-link small{display:block}.controls{margin-top:18px;max-height:45vh;overflow-y:auto}input,select,textarea,button{font:inherit;border:1px solid var(--line);background:var(--paper);color:var(--ink);border-radius:6px;padding:9px}input:not([type=checkbox]),textarea,select{width:100%}textarea{min-height:100px;resize:vertical}button,.button{cursor:pointer;background:var(--accent);color:var(--paper);padding:9px 14px;border:0;text-decoration:none;border-radius:6px;display:inline-block}.filters label{display:block;margin:7px 0}.filters input{margin-right:8px}.filters fieldset{border:0;padding:10px 0;margin:0}.filters legend{font-weight:600}.risk{border-left:4px solid var(--accent);background:var(--soft);padding:14px 18px;border-radius:6px}.steps{display:grid;grid-template-columns:110px 1fr;gap:12px}.steps dt{font-weight:700}.steps dd{margin:0 0 8px}.test-summary{margin:0 0 10px}.test-method{margin:0;padding-left:22px}.test-method li{margin:0 0 8px;padding-left:4px}details{border-top:1px solid var(--line);padding:14px 0}summary{cursor:pointer}.badge{font-size:12px;background:var(--soft);padding:3px 7px;border-radius:4px;display:inline-block}.source-text{white-space:pre-wrap;font-size:14px}nav{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}.empty{padding:28px}.workspace-summary{max-width:1450px;margin:16px auto 0;padding:0 24px;font-size:13px;color:var(--quiet)}@media(max-width:850px){.workspace{grid-template-columns:1fr;padding:14px}.sidebar{position:static}.steps{grid-template-columns:1fr}header{padding:18px;align-items:start;flex-direction:column}}
'''

def render(corpus, params):
    from .relate import Relations

    esc = html.escape
    relations = Relations(corpus)
    selected = scope(params)
    query = (params.get('q') or [''])[0]
    topic = (params.get('topic') or [''])[0]
    assessment = 'technical' if (params.get('assessment') or ['grc'])[0] == 'technical' else 'grc'
    found = matching(query, selected, topic, corpus)
    requested = (params.get('control') or [''])[0]
    chosen = next((c for c in CONTROLS if c['id'] == requested), None) if requested else (found[0] if found else None)
    source_url = '/?' + urlencode({'q': query or (chosen['topic'] if chosen else topic)})
    def checkbox(f, label=None):
        label=label or (corpus.frameworks[f].short_name if f in corpus.frameworks else 'Guidance' if f=='guidance' else f)
        return '<label><input type="checkbox" name="fw" value="%s"%s>%s</label>'%(esc(f),' checked' if f in selected else '',esc(label))
    checkboxes=''
    for f in FRAMEWORKS:
        if f=='essential-eight': continue
        if f=='asd-strategies':
            checkboxes+='<fieldset class="framework-family"><legend>%s</legend>%s%s</fieldset>'%(esc(families.ASD_LABEL),checkbox(f,'Strategies · February 2017'),checkbox('essential-eight','Essential Eight maturity detail · November 2023'))
        else: checkboxes+=checkbox(f)
    listing=''.join('<a class="control-link" href="%s"%s><small>%s</small><strong>%s</strong><small>%d source references</small></a>' %
                    (esc(url(selected,c['id'],query,topic,assessment)), ' aria-current="page"' if chosen and chosen['id']==c['id'] else '',c['id'],esc(c['title']),len(mappings(c,selected))) for c in found)
    topic_options = '<option value="">All topics</option>' + ''.join('<option%s>%s</option>' % (' selected' if t==topic else '',esc(t)) for t in TOPICS)
    sidebar='<aside class="sidebar"><form class="filters" action="/library"><label for="library-q">Find a control</label><input id="library-q" type="search" name="q" value="%s" placeholder="A subject or source identifier"><label for="topic">Topic</label><select id="topic" name="topic" onchange="this.form.requestSubmit()">%s</select><input type="hidden" name="scope" value="1"><div class="controls"><small>%d controls in scope</small>%s</div><p class="muted">%s</p><fieldset><legend>Framework scope</legend>%s</fieldset><button>Apply framework scope</button></form><a href="%s">Export scoped mappings (CSV)</a></aside>' % (esc(query),topic_options,len(found),listing,'' if found else 'No controls match this scope and search.',checkboxes,esc(url(selected,query=query,topic=topic).replace('/library?','/library/export.csv?')))
    main='<section class="box empty"><h2>No control selected</h2><p>Choose frameworks and a control from the list, or search the full source corpus.</p><a href="/?q=%s">Search source corpus</a></section>' % esc(query or 'privileged access')
    sidebar=sidebar.replace('<input type="hidden" name="scope"', '<input type="hidden" name="assessment" value="%s"><input type="hidden" name="scope"'%assessment)
    if chosen:
        c=chosen
        refs=mappings(c,selected)
        # Exact source searches retain the requested source even when its maturity
        # detail is preferred in normal mixed-framework lists.
        exact=next((m for m in mappings(c,selected,False) if m.get('uid','').casefold()==query.casefold()),None)
        if exact and exact not in refs: refs.append(exact)
        test_method='<p class="test-summary">%s</p><ol class="test-method">%s</ol>' % (
            esc(c['test']),
            ''.join('<li>%s</li>' % esc(step) for step in c.get('test_steps', [])),
        )
        rows=[]
        for m in refs:
            source=corpus.control(m['uid']) if 'uid' in m else None
            guidance=corpus.guidance.get(m.get('guidance',''))
            label=('%s %s' % (corpus.frameworks[source.framework_key].short_name,source.identifier)) if source else ('%s — %s' % (guidance.publisher,guidance.title) if guidance else m.get('uid','Unknown source'))
            body='<p class="source-text">%s</p>' % esc(relations.quotable_text(source.uid)) if source else ('<p class="source-text">%s</p>' % esc(m['excerpt']) if guidance else '<p>Source text is not loaded in this build. This reference cannot be assessed here.</p>')
            if source:
                body+=publisher_guidance.render(source)
                body+='<p><a href="/?%s">Open source control, assessment methods and linked controls →</a></p>' % esc(urlencode({'q':source.uid,'view':'cards'}))
                statements=[s for s in corpus.statements_for(source.uid) if s.is_published]
                if statements:
                    body+='<details><summary>Published assessment material (%d)</summary>%s</details>' % (len(statements),''.join('<p><strong>%s</strong></p><p class="source-text">%s</p>'%(esc(s.published_by),esc(s.text)) for s in statements))
            rows.append('<details><summary><strong>%s</strong> <span class="badge">%s</span></summary><p>%s</p><small>%s</small>%s</details>'%(esc(label),esc(m['relationship']),esc(m['basis']),esc(m['provenance']),body))
        attributed = sorted({m['uid'].split(':')[0] for m in refs if 'uid' in m})
        for key in attributed:
            framework = corpus.frameworks.get(key)
            if framework and framework.attribution and corpus.controls_for(key):
                rows.append('<p class="muted">%s</p>' % esc(framework.attribution))
        related=' · '.join('<a href="%s">%s — %s</a>'%(esc(url(selected,uid,assessment=assessment)),uid,esc(next(x['title'] for x in CONTROLS if x['id']==uid))) for uid in c['related'])
        tabs='<nav class="assessment-tabs" aria-label="Assessment focus">'+''.join('<a href="%s#assessment" aria-current="%s">%s</a>'%(esc(url(selected,c['id'],query,topic,mode)),str(assessment==mode).lower(),label) for mode,label in [('grc','GRC'),('technical','Technical')])+'</nav>'
        grc='<dl class="steps"><dt>Examine</dt><dd>%s</dd><dt>Interview</dt><dd>%s</dd><dt>Test</dt><dd>%s</dd><dt>Expected result</dt><dd>%s</dd></dl>'%(esc(c['examine']),esc(c['interview']),test_method,esc(c['expected']))
        assessment_body=workspace_technical.render(c['id'],corpus,selected) if assessment=='technical' else grc+workspace_grc.render(c['id'],corpus,selected)
        main='''<article><section class="box"><div class="eyebrow">%s · %s</div><h2>%s</h2><p>%s</p><p class="muted"><strong>Scope:</strong> %s</p>%s<div class="risk"><strong>Business risk</strong><br>%s</div><nav><a href="#attack">ATT&amp;CK techniques</a><a href="#assessment">Assessment</a><a href="#sources">Source requirements</a></nav></section>
%s
<section class="box" id="assessment"><h3>Assess this control</h3>%s%s</section>%s
<section class="box" id="sources"><h3>Source requirements · %d references in scope</h3>%s</section><section class="box"><h3>Related controls</h3><p>%s</p></section></article>''' % (
            c['id'],esc(c['topic']),esc(c['title']),esc(c['statement']),esc(c['scope']),'<p class="muted">This control has no references in the selected framework scope.</p>' if not refs else '',esc(c['risk']),workspace_attack.render(c['id'],corpus),tabs,assessment_body,wa_audit_context.render(c['id']),len(refs),''.join(rows) or '<p>No source references selected.</p>',related)
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WACC · Control workspace</title><style>%s</style></head><body><header><div><div class="eyebrow">WA Control Crosswalk</div><h1>Control workspace</h1></div><nav><a href="/assessments">Assessments</a><a href="/sources">Sources</a><a href="/frameworks">Framework coverage &amp; checks</a><a href="%s">Browse source corpus →</a></nav></header><p class="workspace-summary">Control library · %d controls across %d topics, with reviewed source connections. The full corpus remains available in the source browser.</p><div class="workspace">%s<main>%s</main></div><script>async function copyAssessmentCommand(button){const code=button.parentElement.querySelector("code");const range=document.createRange();range.selectNodeContents(code);const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);button.textContent="Selected — press Ctrl+C";try{await navigator.clipboard.writeText(code.textContent);button.textContent="Copied";setTimeout(()=>button.textContent="Copy commands",2000);}catch(error){/* Selected text remains available for manual copying. */}}function openCheck(){const el=document.getElementById(decodeURIComponent(location.hash.slice(1)));if(el && el.tagName==="DETAILS")el.open=true;}addEventListener("hashchange",openCheck);openCheck();</script></body></html>' % (STYLE,esc(source_url),len(CONTROLS),len(TOPICS),sidebar,main)
