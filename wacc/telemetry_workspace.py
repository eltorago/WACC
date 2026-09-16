"""Evidence import, annual comparison and reviewer decisions."""
import html
import json
from collections import Counter
from urllib.parse import urlencode
from .control_workspace import STYLE
from .department_workspace import CSS
from .department_assessments import AssessmentError, REQUIREMENTS
from .telemetry import SOURCES, TABLES, ValidationStore
from .telemetry_policy import policy_coverage

esc = lambda value: html.escape(str(value), quote=True)
COLORS = {'support':'#28724a', 'gap':'#b23d32', 'review':'#9b6b12', 'none':'#8a929d'}
CSS_EXTRA = '''
.validation-status{display:inline-block;padding:5px 10px;border-radius:5px;background:var(--soft);font-size:13px;font-weight:600}.validation-status.gap{background:#fce7e4;color:#932d25}.validation-status.support{background:#e5f2ea;color:#18532e}.validation-status.review{background:#fff4d6;color:#77500c}.validation-card{border-top:1px solid var(--line);padding:22px 0}.validation-card:first-of-type{border-top:0}.validation-card h3{margin:8px 0}.validation-card pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;background:var(--soft);padding:14px;font-size:12px}.validation-review{display:grid;gap:10px;max-width:700px}.validation-review label{font-size:13px}.validation-review textarea{min-height:80px;width:100%;box-sizing:border-box}.validation-review input,.validation-review select{width:100%;box-sizing:border-box}.evidence-strip{display:flex;height:10px;min-width:150px;border-radius:4px;overflow:hidden;margin:8px 0}.evidence-strip span{display:block}.validation-steps{padding-left:20px}.validation-steps li{margin:8px 0}.validation-scope{overflow-wrap:anywhere}.review-history{border-left:3px solid var(--line);padding-left:14px;margin:15px 0}.validation-links a{margin-right:14px}.validation-help{font-size:13px;color:var(--quiet)}
'''


def category(status):
    return 'gap' if status in ('Potential overstatement', 'Gap observed') else 'support' if status == 'Supports observed operation' else 'none' if status == 'No evidence' else 'review'


def counts(report):
    return Counter(category(f['status']) for f in report['findings'])


def strip(report):
    c = counts(report)
    label = f'{len(report["findings"])} checks: {c["support"]} supported, {c["gap"]} gaps, {c["review"]} need review, {c["none"]} without evidence'
    pieces = ''.join(f'<span style="background:{color};width:{c[key]/len(report["findings"])*100}%"></span>' for key, color in COLORS.items())
    return f'<div class="evidence-strip" role="img" aria-label="{label}">{pieces}</div><small>{label}</small>'


def assessment_panel(store, years, selected):
    reports = ValidationStore(store).all()
    rows = []
    for record in years:
        latest = next((r for r in reports if r['assessment_key'] == record['key']), None)
        if not latest: status = 'Not validated'
        elif latest['assessment_sha256'] != record['sha256']: status = 'Assessment changed — validate again'
        else: status = strip(latest)
        target = '/assessments/validation?' + urlencode({'assessment':record['key']})
        rows.append(f'<tr><th><a href="{esc(target)}">{record["year"]}</a></th><td>{status}</td></tr>')
    return f'''<section class="box"><style>{CSS_EXTRA}</style><h2>Validate against security logs</h2><p>Compare reported ratings with Sentinel and Defender evidence. Review possible overstatements and retain the event trail.</p><p><a href="/assessments/validation?assessment={selected['key']}">Validate the {selected['year']} assessment →</a></p><div class="table-wrap"><table><caption>Telemetry checks by assessment year</caption><thead><tr><th>Year</th><th>Latest evidence findings</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''


def _finding(f, run, token, stale):
    links = ' · '.join(f'<a href="/library?control={esc(c)}">{esc(c)}</a>' for c in f['controls'])
    policies = []
    for key, rating in f['policies'].items():
        source = '/?' + urlencode({'q':'wa-csp:'+key, 'view':'cards'})
        policies.append(f'<a href="{esc(source)}">WA CSP {esc(key)}</a> · reported {esc(rating)} · {esc(REQUIREMENTS[key]["prompt"])}')
    evidence = []
    for e in f['evidence'][:20]:
        row = e['row']; identity = (row.get('DeviceName') or row.get('UserPrincipalName') or row.get('BackupItemFriendlyName')
                                   or row.get('Title') or row.get('SourceIp') or row.get('DeviceId') or row.get('UserId') or row.get('Id') or e['table'])
        action = row.get('ActionType') or row.get('ActivityDisplayName') or row.get('JobOperation') or row.get('Action') or e['table']
        label = f'{e["time"]} · {identity} · {action}'
        evidence.append(f'<details><summary>{esc(label)}</summary><p class="validation-help">{esc(e["file"])} · line {e["line"]} · canonical event SHA-256 {esc(e["sha256"])}</p>'
                        +(f'<p>{esc(e["test_reference"])}</p>' if e.get('test_reference') else '')
                        +f'<pre>{esc(json.dumps(row, indent=2, ensure_ascii=False))}</pre></details>')
    more = f'<p>Showing 20 of {len(f["evidence"])} event references. Download the report for all references.</p>' if len(f['evidence'])>20 else ''
    history = ''.join(f'<div class="review-history"><strong>{esc(r["decision"])}</strong><p>{esc(r["note"])}</p><small>{esc(r["reviewer"])} · {esc(r["at"])}</small></div>' for r in f['reviews'])
    form = '' if stale else f'''<details><summary>Record a review decision</summary><form class="validation-review" data-validation-action method="post" action="/assessments/validation/review">
<input type="hidden" name="token" value="{token}"><input type="hidden" name="run" value="{run['id']}"><input type="hidden" name="finding" value="{f['id']}">
<label>Decision<select name="decision"><option>More evidence needed</option><option>Confirmed gap</option><option>Explained exception</option><option>Evidence accepted</option></select></label>
<label>Reviewer<input name="reviewer" maxlength="120" required></label><label>Reason and evidence reference<textarea name="note" maxlength="2000" required></textarea></label><button>Save review</button><p role="status"></p></form></details>'''
    return f'''<article class="validation-card" id="{f['id']}"><span class="validation-status {category(f['status'])}">{esc(f['status'])}</span><h3>{esc(f['title'])}</h3><p>{links}</p><p>{esc(f['summary'])}</p><p><strong>Next step:</strong> {esc(f['action'])}</p><details><summary>Compared with the self-assessment</summary>{''.join('<p>'+p+'</p>' for p in policies)}</details><details><summary>Event evidence ({len(f['evidence'])})</summary>{''.join(evidence) or '<p>No matching event was supplied.</p>'}{more}</details><p class="validation-help"><a href="{esc(f['sources'][0])}">Microsoft reference</a> · {f['id']}</p>{history}{form}</article>'''


def _coverage(run):
    coverage = policy_coverage(run)
    mapped = sum(bool(r['checks']) for r in coverage)
    rows = []
    for r in coverage:
        source = '/?' + urlencode({'q':'wa-csp:'+r['id'],'view':'cards'})
        links = ' · '.join(f'<a href="#{id_}">{id_}</a>' for id_ in r['checks']) or 'Document or separate test required'
        rows.append(f'<tr><th><a href="{esc(source)}">{r["id"]}</a><small>{esc(r["area"])}</small></th><td>{esc(r["prompt"])}</td><td>{links}</td><td>{esc(r["evidence"])}</td></tr>')
    return f'<section class="box"><h2>WA policy coverage</h2><p>{mapped} of {len(coverage)} policy criteria have contributing log checks in this run. The table identifies the documents or separate tests needed for the rest.</p><details><summary>View all 86 policy criteria and evidence sources</summary><div class="table-wrap"><table><thead><tr><th>Policy</th><th>Requirement</th><th>Log checks</th><th>Document to review</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div></details></section>'


def render(store, token, params=None):
    params = params or {}; records = store.all(); validations = ValidationStore(store)
    requested_run = (params.get('run') or [''])[0]
    run = validations.get(requested_run) if requested_run else None
    if requested_run and not run: raise AssessmentError('This validation run does not exist.')
    key = run['assessment_key'] if run else (params.get('assessment') or [''])[0]
    record = next((a for a in records if a['key'] == key), None)
    if key and not record: raise AssessmentError('This assessment does not exist.')
    if not record and records: record = sorted(records, key=lambda a:(a['department'].casefold(), -a['year']))[0]
    if record and not run: run = next(iter(validations.all(record['key'])), None)
    options = ''.join(f'<option value="{a["key"]}" {"selected" if record and a["key"]==record["key"] else ""}>{a["year"]} · {esc(a["department"])}</option>' for a in sorted(records, key=lambda a:(a['department'].casefold(), -a['year'])))
    downloads = ''.join(f'<a href="/assessments/validation/example?year={y}">Silly Walks · {y} logs</a>' for y in (2023,2024,2025))
    demo = bool(record and record['department']=='Department of Silly Walks' and record['year'] in (2023,2024,2025))
    sidebar = f'''<aside><section class="box"><h2>Validate an assessment</h2><form method="get"><label for="selected-assessment">Department and year</label><select id="selected-assessment" name="assessment" onchange="this.form.submit()">{options}</select></form>
<ol class="validation-steps"><li>Declare the devices, users, apps and evidence dates in <code>manifest.json</code>.</li><li>Choose relevant Sentinel or Defender exports in JSON lines or CSV.</li><li>Import, inspect each finding and record a review decision.</li></ol>
<form data-validation-action class="assessment-form" method="post" action="/assessments/validation/import" enctype="multipart/form-data"><input type="hidden" name="token" value="{token}"><input type="hidden" name="assessment" value="{record['key'] if record else ''}"><label for="telemetry-files">Manifest and event files, or example bundle</label><input type="file" id="telemetry-files" name="files" accept=".json,.jsonl,.csv" multiple required><button {'disabled' if not record else ''}>Import and validate</button><p role="status"></p></form><p class="validation-help">Up to 20 MB and 50,000 rows per run. Evidence stays in the local assessment folder.</p></section>
<section class="box"><h3>Fictional examples</h3><div class="download-list">{downloads}</div><form data-validation-action method="post" action="/assessments/validation/demo"><input type="hidden" name="token" value="{token}"><input type="hidden" name="assessment" value="{record['key'] if record else ''}"><button {'disabled' if not demo else ''}>Validate this year’s example logs</button><p role="status"></p></form><p class="validation-help">Import the Silly Walks assessment workbooks first. The 2025 logs include two possible overstatements.</p></section>
<section class="box"><h3>Example sources</h3><p>The examples use twelve documented table schemas with fictional values. They work offline; no Azure connection is needed.</p><p>ADLS and CSV collection instructions are available for later use with real evidence.</p><p><a href="/assessments/validation/guide">Setup and export guide</a></p><p><a href="/assessments/validation/queries">Download KQL export queries</a></p><p><a href="{SOURCES['wa']}">WA SOC onboarding guidance</a></p></section></aside>'''
    if not record:
        main = '<section class="box"><h2>Import an annual assessment first</h2><p><a href="/assessments">Open department assessments</a> to import a workbook or load the three examples.</p></section>'
    else:
        back = '/assessments?' + urlencode({'department':record['department'], 'year':record['year']})
        main = f'<section class="box"><div class="eyebrow">{record["year"]} evidence validation</div><h2>{esc(record["department"])}</h2><p><a href="{esc(back)}">← Annual assessment and maturity trend</a></p><p>Findings compare observed activity with the reported ratings. Review a possible overstatement to confirm a gap or document an exception.</p></section>'
        if not run:
            main += '<section class="box"><h2>Ready for evidence</h2><p>Import a manifest and log files, or validate this year’s fictional example.</p></section>'
        else:
            m = run['manifest']; q = run['quality']; c = counts(run)
            stale = run['assessment_sha256'] != record['sha256']
            notices = []
            if stale: notices.append('The workbook has changed since this run. Import the logs again before reviewing the current assessment.')
            if m['source_kind']=='fictional-example': notices.append('Fictional demonstration data. These events do not describe a real department or tenant.')
            if q['count_mismatches']: notices.append('Export counts do not reconcile for '+', '.join(q['count_mismatches'])+'. Obtain the missing or corrected export before accepting coverage.')
            if q['unreconciled_tables']: notices.append('No independent source row count supplied for '+', '.join(q['unreconciled_tables'])+'. Export completeness is unverified.')
            if q['conflicting_events']: notices.append(f'{q["conflicting_events"]} event identities have conflicting records. These cannot support a result; reconcile them with the source export.')
            history = validations.all(record['key'])
            run_options = ''.join(f'<option value="{r["id"]}" {"selected" if r["id"]==run["id"] else ""}>{esc(r["created_at"])} · {esc(r["manifest"]["source_kind"])}</option>' for r in history)
            table_rows = ''.join(f'<tr><th>{t}</th><td>{m.get("expected_rows",{}).get(t,"Not supplied")}</td><td>{q["table_rows"].get(t,0)}</td><td>{q["scope_rows"].get(t,0)}</td></tr>' for t in sorted({f['table'] for f in m['files']}))
            files = ''.join(f'<p><strong>{esc(f["name"])}</strong> · {f["bytes"]} bytes<br><code>{f["sha256"]}</code></p>' for f in run['files'])
            main += f'''<section class="box validation-scope">{''.join(f'<p class="notice">{esc(n)}</p>' for n in notices)}<h2>Evidence window</h2><p><strong>{esc(m['start'])} → {esc(m['end'])}</strong> (end exclusive)</p><p>{esc(m['scope_reference'])}</p><p>Declared scope — devices: {len(m['device_ids'])}; users: {len(m['mfa_user_ids'])}; apps: {len(m['mfa_app_ids'])}. Findings cover this sample and time window.</p><div class="metric-row"><div><strong>{c['support']}</strong><span>Observed support</span></div><div><strong>{c['gap']}</strong><span>Possible overstatements / gaps</span></div><div><strong>{c['review']}</strong><span>Need review</span></div><div><strong>{c['none']}</strong><span>No evidence</span></div></div>{strip(run)}
<details><summary>Export coverage and provenance</summary><p>{q['rows']} rows read · {q['duplicates']} exact duplicates · {q['outside_window']} outside the window · {q['outside_scope']} outside the declared scope.</p><p>Observed events: {esc(q['first_event'] or 'none')} → {esc(q['last_event'] or 'none')}.</p><p>Workspace: {esc(m['workspace_id'])}<br>Entra tenant: {esc(m['entra_tenant_id'])}</p><div class="table-wrap"><table><thead><tr><th>Table</th><th>Source count</th><th>Imported in window</th><th>Unique in scope</th></tr></thead><tbody>{table_rows}</tbody></table></div>{files}<p>Rules: {run['rule_version']}<br>Assessment SHA-256: <code>{run['assessment_sha256']}</code></p></details><p><a href="/assessments/validation/report?run={run['id']}">Download findings and review history (JSON)</a></p><form method="get"><label for="validation-run">Saved runs</label><select id="validation-run" name="run" onchange="this.form.submit()">{run_options}</select></form></section>{_coverage(run)}<section class="box"><h2>Review the findings</h2>{''.join(_finding(f,run,token,stale) for f in run['findings'])}</section>'''
    script = '''<script>document.querySelectorAll('[data-validation-action]').forEach(form=>form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button'),status=form.querySelector('[role=status]');button.disabled=true;status.textContent='Checking evidence…';try{const response=await fetch(form.action,{method:'POST',body:new FormData(form)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Validation failed.');location.assign(result.location);}catch(error){status.textContent=error.message;button.disabled=false;}}));</script>'''
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WACC · Assessment validation</title><style>{STYLE}{CSS}{CSS_EXTRA}</style></head><body><header><div><div class="eyebrow">WA Control Crosswalk</div><h1>Assessment validation</h1></div><nav><a href="/assessments">Assessments</a><a href="/library">Control workspace</a></nav></header><main class="assessment-page"><div class="assessment-grid">{sidebar}<div class="assessment-main">{main}</div></div></main>{script}</body></html>'
