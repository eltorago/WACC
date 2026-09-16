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
    return json.dumps([{k:v for k,v in c.items() if k not in ('references','sources')} for c in for_control(control_id)])


def source_mappings(control_id):
    out={}
    for check in for_control(control_id):
        for uid in check['references']:
            out[uid]={'uid':uid,'relationship':'Partially addresses',
                      'provenance':'Locally reviewed mapping',
                      'basis':'Technical assessment '+check['id']+' addresses this source within '+check['platform']+'. Confirm the source scope, edition and local applicability.'}
    return list(out.values())


def render(control_id,corpus,selected):
    esc=html.escape
    checks=for_control(control_id)
    intro='<p>Individual technical checks · %d. Each check supports this control within its stated platform and scope. These are locally authored assessment methods, not publisher certification tests.</p><p class="muted">Read-only examples collect configuration evidence; WACC does not execute them. Use the prerequisites and a permitted test environment for behavioural tests. A query error, inaccessible system or incomplete population means unknown, not pass.</p>'%len(checks)
    items=[]
    for c in checks:
        procedure=c['execution']
        links=[]
        for key in c['sources']:
            title,url=SOURCES[key]
            links.append('<a href="%s">%s</a>'%(esc(url),esc(title)))
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
        setup=''.join('<p>%s</p>'%esc(PROCEDURES['profiles'][profile]) for profile in procedure['profile'].split('+'))
        if procedure.get('scopes'): setup+='<p><strong>Graph delegated permissions:</strong> %s</p>'%esc(procedure['scopes'])
        if procedure.get('inputs'): setup+='<p><strong>Inputs:</strong> %s</p>'%esc(procedure['inputs'])
        validation=procedure.get('validation',{})
        validation_text=validation.get('summary','Command validation has not been recorded; review before use.')
        command=('<h4>Run this check</h4>%s<p>Save the example as a .ps1 file in your approved assessment folder and run it in the console above. It prompts for scoped inputs. Review output for missing fields and errors; neither means pass. Commands read configuration or supplied exports; the AppLocker example also writes a local XML evidence file.</p><details><summary>PowerShell collection example</summary><button type="button" class="copy-command" onclick="copyAssessmentCommand(this)">Copy commands</button><pre><code>%s</code></pre></details><p><strong>Command references:</strong> %s</p><p class="muted"><strong>Validation:</strong> %s</p>'%(setup,esc(c['command']),' · '.join(command_links),esc(validation_text))) if c.get('command') else ''
        context='<p class="muted">%s</p>'%esc(c['vendor_context']) if c.get('vendor_context') else ''
        items.append('''<details class="technical-check" id="%s"><summary><span class="badge">%s</span> <strong>%s</strong><small> · %s</small></summary>
<p>%s</p><h4>Prerequisites and access</h4><p>%s</p><h4>Artefacts to inspect</h4><ul>%s</ul>%s
<h4>Test steps</h4><ol>%s</ol><h4>Expected result</h4><p>%s</p><h4>Interpretation and limits</h4><p>%s</p>%s
<p><strong>Sources:</strong> %s</p>%s</details>''' %
            (esc(c['id']),esc(c['id']),esc(c['title']),esc(c['platform']),esc(c['statement']),esc(c['prerequisites']),
             ''.join('<li>%s</li>'%esc(x) for x in c['artifacts']),command,
             ''.join('<li>%s</li>'%esc(x) for x in c['steps']),esc(c['expected']),esc(c['limitations']),context,
             ' · '.join(links),'<p><strong>Requirements in scope:</strong> '+ ' · '.join(refs)+'</p>' if refs else ''))
    if any(c.get('vendor_context') for c in checks):
        intro+='<p class="muted">AD checks reference selected public PingCastle and Purple Knight criteria. Their engines, scoring, proprietary detection logic and complete coverage are not reproduced. PingCastle references use the dated public 3.3.0.1 list; Purple Knight references use the public 4.2 Community list.</p>'
    return intro+''.join(items)
