"""Source-informed technical assessments; no scanning or tenant writes."""
import html
import json
from pathlib import Path
from urllib.parse import urlencode

ROOT=Path(__file__).resolve().parents[1]
CHECKS=[]
SOURCES={}
for name in ('workspace-technical.json','workspace-technical-ad.json','workspace-technical-cloud.json'):
    data=json.loads((ROOT/'data'/name).read_text(encoding='utf-8'))
    CHECKS.extend(data['checks'])
    SOURCES.update(data['sources'])

PROCEDURES=json.loads((ROOT/'data/assessment-procedures.json').read_text(encoding='utf-8'))
COMMAND_SOURCES=json.loads((ROOT/'data/assessment-sources.json').read_text(encoding='utf-8'))
for check in CHECKS:
    procedure=PROCEDURES['checks'][check['id']]
    check['command']=procedure['command']
    check['steps']=procedure['run_steps']
    check['expected']=procedure['decision']
    check['limitations']=procedure['limits']
    check['execution']=procedure


def for_control(control_id):
    return sorted((c for c in CHECKS if control_id in c['parents']),key=lambda c:c['title'].casefold())


def search_text(control_id):
    # Source identifiers belong to scoped mappings, not unscoped technical text.
    return json.dumps([{k:v for k,v in c.items() if k not in ('references','sources','execution')} for c in for_control(control_id)])


def source_mappings(control_id):
    out={}
    for check in for_control(control_id):
        for uid in check['references']:
            out[uid]={'uid':uid,'relationship':'Partially addresses',
                      'provenance':'Locally reviewed mapping',
                      'basis':check['id']+' · '+check['platform']}
    return list(out.values())


def render(control_id,corpus,selected):
    esc=html.escape
    checks=for_control(control_id)
    intro='<p>%d technical checks</p>'%len(checks)
    profiles=sorted({p for c in checks for p in c['execution']['profile'].split('+')})
    intro+='<details class="assessment-setup"><summary>Console setup and validation</summary><p>Save commands as a .ps1 file and run them in the indicated console. Record the device/tenant, time and scope. Use test accounts and harmless data for behaviour tests. Missing evidence or query errors mean unknown.</p>'
    intro+=''.join('<p id="setup-%s"><strong>%s:</strong> %s</p>'%(esc(p),esc(p.title()),esc(PROCEDURES['profiles'][p])) for p in profiles)
    intro+='<p>Validation: official command references, PowerShell 5.1/7 syntax and offline fixtures. Live AD/M365/Azure behaviour still needs testing in your environment.</p></details>'
    items=[]
    for c in checks:
        procedure=c['execution']
        links=[]
        for key in c['sources']:
            title,url=SOURCES[key]
            links.append('<a href="%s">%s</a>'%(esc(url),esc(title)))
        if c.get('criteria'):
            links.insert(0,esc(c['criteria']))
        command_links=[]
        for key in procedure['sources']:
            source=COMMAND_SOURCES[key]
            command_links.append('<a href="%s">%s</a>'%(esc(source['url']),esc(source['title'])))
        refs=[]
        for uid in c['references']:
            if uid.split(':')[0] not in selected:
                continue
            source=corpus.control(uid)
            if source:
                refs.append('<a href="/?%s">%s %s</a>'%(esc(urlencode({'q':uid,'view':'cards'})),esc(corpus.frameworks[source.framework_key].short_name),esc(source.identifier)))
            else:
                refs.append(esc(uid)+' (source not loaded)')
        setup='<p><strong>Console:</strong> '+', '.join('<a href="#setup-%s" onclick="document.querySelector(\'.assessment-setup\').open=true">%s</a>'%(esc(p),esc(p.title())) for p in procedure['profile'].split('+'))+'</p>'
        if procedure.get('scopes'): setup+='<p><strong>Graph delegated permissions:</strong> %s</p>'%esc(procedure['scopes'])
        if procedure.get('inputs'): setup+='<p><strong>Inputs:</strong> %s</p>'%esc(procedure['inputs'])
        command=('<details><summary>PowerShell commands</summary>%s<button type="button" class="copy-command" onclick="copyAssessmentCommand(this)">Copy commands</button><pre><code>%s</code></pre></details>'%(setup,esc(c['command']))) if c.get('command') else ''
        items.append('''<details class="technical-check" id="%s"><summary><span class="badge">%s</span> <strong>%s</strong><small> · %s</small></summary>
<h4>Before you start</h4><p>%s</p><h4>Steps</h4><ol>%s</ol><h4>Expected result</h4><p>%s</p><p class="muted">%s</p>%s
<details><summary>Evidence and sources</summary><ul>%s</ul><p>%s</p>%s</details></details>''' %
            (esc(c['id']),esc(c['id']),esc(c['title']),esc(c['platform']),esc(c['prerequisites']),
             ''.join('<li>%s</li>'%esc(x) for x in c['steps']),esc(c['expected']),esc(c['limitations']),command,
             ''.join('<li>%s</li>'%esc(x) for x in c['artifacts']),
             ' · '.join(dict.fromkeys(command_links+links)),'<p><strong>Requirements in scope:</strong> '+ ' · '.join(refs)+'</p>' if refs else ''))
    return intro+''.join(items)
