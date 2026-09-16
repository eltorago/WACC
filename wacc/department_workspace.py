"""Department assessment imports, yearly comparisons and requirement details."""
import html
from urllib.parse import urlencode
from .control_workspace import STYLE, CONTROLS
from .department_assessments import POLICY, REQUIREMENTS, RATINGS, DOWNLOADS, scores, comparable_ids

esc=lambda value: html.escape(str(value),quote=True)

CSS='''
.assessment-page{max-width:1450px;margin:auto;padding:24px}.assessment-grid{display:grid;grid-template-columns:290px minmax(0,1fr);gap:24px}.assessment-grid aside{align-self:start}.assessment-main{min-width:0}.assessment-main .box{padding:24px}.assessment-form label{display:block;margin:14px 0 5px}.assessment-form input[type=checkbox]{width:auto}.assessment-form button{margin-top:12px}.download-list a{display:block;padding:5px 0}.metric-row{display:flex;gap:36px;flex-wrap:wrap;margin:18px 0 24px}.metric-row strong{font-size:30px;display:block;line-height:1.2}.metric-row span{color:var(--quiet);font-size:13px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:12px;border-bottom:1px solid var(--line);vertical-align:top}th{font-weight:600;color:var(--quiet)}caption{text-align:left;font-weight:600;margin:12px 0}td p{margin:3px 0}td small{display:block}.trend{width:100%;height:auto;max-height:330px}.notice{padding:12px 16px;border-left:4px solid var(--accent);background:var(--soft);margin-bottom:18px}.error{border-left-color:#b42318;background:#fff0ee;color:#842119}.year-nav a{border:1px solid var(--line);border-radius:6px;padding:6px 13px;text-decoration:none}.year-nav a[aria-current=page]{background:var(--accent);color:var(--paper)}.rating{display:inline-block;white-space:nowrap;padding:4px 9px;border-radius:4px;background:var(--soft)}.rating-0,.rating-1{background:#fff0df;color:#784400}.rating-2{background:#fff5d9;color:#735900}.rating-3,.rating-4{background:#e5f2ea;color:#18532e}.area-bar{height:6px;background:var(--line);border-radius:3px;width:100%;min-width:75px;margin-top:6px}.area-bar i{display:block;height:6px;background:var(--accent);border-radius:3px}.import-status{min-height:24px}a:focus-visible,button:focus-visible{outline:3px solid #438fd5;outline-offset:3px}.assessment-main summary{font-weight:600}.assessment-main details{padding:16px 0}.assessment-main h3{margin-top:18px}.assessment-main .gap{color:#965a00} @media(max-width:950px){.assessment-grid{grid-template-columns:1fr}.assessment-page{padding:14px}.assessment-grid aside{position:static}.metric-row{gap:20px}}
'''


def _number(value):
    return 'Not assessed' if value is None else f'{value:.2f}'


def _url(department,year=None,area=None):
    params={'department':department}
    if year: params['year']=year
    if area: params['area']=area
    return '/assessments?'+urlencode(params)


def _trend(records,ids):
    points=[]; nodes=[]
    for i,record in enumerate(records):
        x=75+(record['year']-records[0]['year'])*680/(records[-1]['year']-records[0]['year']) if len(records)>1 else 415
        value=scores(record,ids=ids)['score']
        nodes.append(f'<text x="{x}" y="272" text-anchor="middle">{record["year"]}</text>')
        if value is None:
            nodes.append(f'<text x="{x}" y="235" text-anchor="middle" font-size="12">Incomplete</text>')
            points.append(None)
        else:
            y=240-value*50
            points.append((x,y))
            nodes.append(f'<circle cx="{x}" cy="{y}" r="6" fill="var(--accent)"/><text x="{x}" y="{y-16}" text-anchor="middle" font-weight="600">{value:.2f}</text>')
    lines=[]
    for before,after in zip(points,points[1:]):
        if before and after: lines.append(f'<line x1="{before[0]}" y1="{before[1]}" x2="{after[0]}" y2="{after[1]}" stroke="var(--accent)" stroke-width="3"/>')
    grid=''.join(f'<line x1="55" y1="{240-n*50}" x2="780" y2="{240-n*50}" stroke="var(--line)"/><text x="35" y="{245-n*50}">{n}</text>' for n in range(5))
    desc='; '.join(f'{a["year"]}: {_number(scores(a,ids=ids)["score"])}' for a in records)
    return f'<svg class="trend" viewBox="0 0 830 290" role="img" aria-labelledby="trend-title trend-desc"><title id="trend-title">Self-assessment maturity, 0 to 4</title><desc id="trend-desc">{esc(desc)}</desc><g fill="var(--quiet)" font-family="Segoe UI,sans-serif" font-size="14">{grid}{"".join(lines)}{"".join(nodes)}</g></svg>'


def _detail(record,area):
    controls={}
    for c in CONTROLS:
        for m in c['mappings']:
            uid=m.get('uid','')
            if uid.startswith('wa-csp:'): controls.setdefault(uid[7:],[]).append(c)
    body=[]
    for row in record['rows']:
        req=REQUIREMENTS[row['id']]
        if area and req['area']!=area: continue
        links=[]
        for key in (row['id'],req['section']):
            for c in controls.get(key,[]):
                link=f'<a href="/library?control={esc(c["id"])}">{esc(c["id"])} · {esc(c["title"])}</a>'
                if link not in links: links.append(link)
        rating=row['rating']
        source='/?'+urlencode({'q':'wa-csp:'+row['id'],'view':'cards'})
        body.append(f'<tr><td><a href="{esc(source)}">{esc(row["id"])}</a><small>{esc(req["area"])}</small></td><td>{esc(req["prompt"])}'
                    +(f'<details><summary>Related controls</summary>{"<br>".join(links)}</details>' if links else '')
                    +f'</td><td><span class="rating rating-{esc(rating)}">{esc(rating+" · " if rating.isdigit() else "")}{esc(RATINGS[rating])}</span></td>'
                    +f'<td>{esc(row["evidence"]) or "—"}'+(f'<p><strong>Exclusion:</strong> {esc(row["exclusion"])}</p>' if rating=='N/A' else '')+'</td>'
                    +f'<td>{esc(row["action"]) or "—"}<small>{esc(row["owner"])}{(" · "+esc(row["due"])) if row["due"] else ""}</small></td></tr>')
    return '<div class="table-wrap"><table><thead><tr><th>Policy</th><th>Assessment criterion</th><th>Rating</th><th>Evidence</th><th>Next action / owner / due</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div>'


def render(store,token,params=None,message='',error=False):
    params=params or {}; records=store.all()
    departments=sorted({r['department'] for r in records},key=str.casefold)
    selected=(params.get('department') or [departments[0] if departments else ''])[0]
    if selected not in departments: selected=departments[0] if departments else ''
    years=sorted([r for r in records if r['department'].casefold()==selected.casefold()],key=lambda r:r['year'])
    year=(params.get('year') or [str(years[-1]['year']) if years else ''])[0]
    record=next((r for r in years if str(r['year'])==year),years[-1] if years else None)
    area=(params.get('area') or [''])[0]
    if area not in POLICY['areas']: area=''
    notice=f'<div class="notice {"error" if error else ""}" role="{ "alert" if error else "status" }">{esc(message)}</div>' if message else ''
    options=''.join(f'<option {"selected" if d==selected else ""}>{esc(d)}</option>' for d in departments)
    downloads=''.join(f'<a href="/assessments/download/{name}">{"Blank assessment template" if "template" in name else "Silly Walks · "+name[-9:-5]}</a>' for name in DOWNLOADS)
    sidebar=f'''<aside><section class="box"><h2>Import assessments</h2><form id="assessment-import" class="assessment-form" method="post" enctype="multipart/form-data" action="/assessments/import">
<input type="hidden" name="token" value="{token}"><label for="assessment-files">Workbooks (.xlsx, up to 5 MB each)</label><input id="assessment-files" type="file" name="files" accept=".xlsx" multiple required>
<label><input type="checkbox" name="replace" value="1"> Replace existing years</label><button>Import selected files</button></form><p id="import-status" class="import-status" role="status"></p>
<details><summary>How to prepare a workbook</summary><p>Download the blank template. Complete the department and year, then rate each requirement and record the supporting evidence. Keep the headings and requirement IDs.</p><p>Use N/A with an exclusion reason, or Not assessed for outstanding work. Select several annual workbooks to compare years.</p></details></section>
<section class="box"><h3>Template and examples</h3><div class="download-list">{downloads}</div><form method="post" action="/assessments/examples"><input type="hidden" name="token" value="{token}"><button>Import the three examples</button></form><p class="muted">Department of Silly Walks is fictional. The 2023 example applies the 2024 policy retrospectively.</p></section></aside>'''
    if not record:
        main='<section class="box empty"><div class="eyebrow">WA Cyber Security Policy 2024</div><h2>See how security maturity changes</h2><p>Import a department’s annual assessments to compare its six policy areas and review the evidence behind each rating.</p><p>Start with the three Department of Silly Walks examples, or download a blank template.</p></section>'
    else:
        from .telemetry_workspace import assessment_panel
        metric=scores(record); ids=comparable_ids(years)
        reporting=record.get('reporting',{})
        reporting_view='<details><summary>Approval and reporting</summary>'+''.join(
            f'<p><strong>{label}:</strong> {esc(reporting.get(key) or "Not recorded")}</p>'
            for label,key in [('Accountable authority','authority'),('Approval date','approval_date'),
                              ('AIR status','air_status'),('AIR reference','air_reference'),('Exemptions','exemptions')])+'</details>'
        baseline=scores(years[0],ids=ids)['score']
        current=scores(record,ids=ids)['score']
        change=f'{current-baseline:+.2f}' if current is not None and baseline is not None else '—'
        nav=''.join(f'<a href="{esc(_url(selected,r["year"]))}" {"aria-current=page" if r["year"]==record["year"] else ""}>{r["year"]}</a>' for r in years)
        rows=[]
        for a in POLICY['areas']:
            cells=''
            for r in years:
                s=scores(r,area=a)
                bar=f'<div class="area-bar"><i style="width:{s["score"]*25}%"></i></div>' if s['score'] is not None else ''
                cells+=f'<td><a href="{esc(_url(selected,r["year"],a))}">{_number(s["score"])}</a>{bar}<small>{s["rated"]} rated · {s["excluded"]} excluded</small></td>'
            rows.append(f'<tr><th>{a}</th>{cells}</tr>')
        area_options='<option value="">All policy areas</option>'+''.join(f'<option {"selected" if a==area else ""}>{a}</option>' for a in POLICY['areas'])
        scope_changed=len({r['scope'] for r in years})>1
        main=f'''<section class="box"><form method="get"><label for="department">Department</label><select id="department" name="department" onchange="this.form.submit()">{options}</select></form><nav class="year-nav">{nav}</nav>
<div class="eyebrow">{record['year']} assessment</div><h2>{esc(selected)}</h2><p>{esc(record['scope'])}</p>
<div class="metric-row"><div><strong>{_number(metric['score'])}<small>{' / 4' if metric['score'] is not None else ''}</small></strong><span>Average maturity rating</span></div><div><strong>{metric['rated']} / {metric['total']-metric['excluded']}</strong><span>Applicable requirements rated</span></div><div><strong>{metric['implemented']}</strong><span>Implemented or tested</span></div><div><strong>{change}</strong><span>Change since {years[0]['year']}</span></div></div>
<p class="muted">Assessed {record['date']} · {esc(record['assessor'])}{' · Retrospective assessment' if record['retrospective']=='Yes' else ''}</p>{reporting_view}</section>
{assessment_panel(store,years,record)}
<section class="box"><h2>Maturity over time</h2><p class="muted">WACC self-assessment scale, 0–4. Comparing the same {len(ids)} applicable requirements across all years.</p>{_trend(years,ids)}
{'<p class="notice">The declared scope changes between years. Review the scope for each assessment when comparing results.</p>' if scope_changed else ''}
<div class="table-wrap"><table><caption>Policy areas</caption><thead><tr><th>Area</th>{''.join(f'<th>{r["year"]}</th>' for r in years)}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<details><summary>Rating scale and calculation</summary><p>WACC uses 0 Not started, 1 Planned, 2 Partly implemented, 3 Implemented and 4 Tested and reviewed. This is an assessment progress scale, not an official WA or Essential Eight maturity level.</p><p>Each requirement has equal weight. A score is shown only when all applicable requirements are rated. N/A rows are excluded. The trend compares requirements applicable in every year; area scores use that year's applicable requirements.</p><p>Criteria are WACC summaries of all 86 policy requirement records. <a href="{POLICY['source_url']}">Read the 2024 policy</a>.</p></details></section>
<section class="box"><h2>{record['year']} requirement assessments</h2><form method="get"><input type="hidden" name="department" value="{esc(selected)}"><input type="hidden" name="year" value="{record['year']}"><label for="area">Policy area</label><select id="area" name="area" onchange="this.form.submit()">{area_options}</select></form>{_detail(record,area)}<p class="muted">Imported from {esc(record['filename'])}. Workbook SHA-256: <code>{record['sha256']}</code></p></section>'''
    script='''<script>document.getElementById('assessment-import').addEventListener('submit',async function(event){event.preventDefault();const button=this.querySelector('button');const status=document.getElementById('import-status');button.disabled=true;status.textContent='Checking and importing workbooks…';try{const response=await fetch(this.action,{method:'POST',body:new FormData(this)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Import failed.');location.assign(result.location);}catch(error){status.textContent=error.message;button.disabled=false;}});</script>'''
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WACC · Department assessments</title><style>{STYLE}{CSS}</style></head><body><header><div><div class="eyebrow">WA Control Crosswalk</div><h1>Department assessments</h1></div><nav><a href="/library">Control workspace</a><a href="/sources">Sources</a><a href="/frameworks">Framework coverage</a></nav></header><main class="assessment-page">{notice}<div class="assessment-grid">{sidebar}<div class="assessment-main">{main}</div></div></main>{script}</body></html>'
