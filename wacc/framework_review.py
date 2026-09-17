"""Display loaded editions and the reproducible cloud-framework gap review."""
import html
import json
from pathlib import Path
from urllib.parse import urlencode


def render(corpus):
    from .control_workspace import STYLE
    from .workspace_technical import CHECKS
    from .wa_audit_context import REPORTS
    from .framework_families import ASD_LABEL
    esc=html.escape
    review=json.loads((Path(__file__).resolve().parents[1]/'data/framework-review.json').read_text(encoding='utf-8'))
    rows=[]
    for key in ('asd-principles','asd-strategies','mcsb','scuba','scf'):
        fw=corpus.frameworks[key]
        count=len(corpus.controls_for(key))
        if key=='asd-strategies':
            e8=corpus.frameworks['essential-eight']
            rows.append('<li><strong>%s</strong><ul><li><a href="%s">37 strategies</a> · %s · %d records loaded</li><li><a href="%s">Essential Eight maturity detail</a> · %s · %d records loaded</li></ul></li>'%(esc(ASD_LABEL),esc(fw.source_url),esc(fw.revision),count,esc(e8.source_url),esc(e8.revision),len(corpus.controls_for(e8.key))))
        else:
            rows.append('<li><a href="%s">%s</a> · %s · %s</li>'%(esc(fw.source_url),esc(fw.name),esc(fw.revision),('%d records loaded'%count if count else 'Source not loaded — run python -m wacc sources')))
    priorities=''.join('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%d</td><td>%s</td></tr>'%(esc(x['source_url']),esc(x['title']),esc(x['status']),x['mapped_scf_controls'],esc(x['reason'])) for x in review['priorities'])
    checks=''.join('<li><a href="/library?%s#%s">%s — %s</a><small> · %s</small></li>'%(esc(urlencode({'control':c['parents'][0],'assessment':'technical'})),esc(c['id']),esc(c['id']),esc(c['title']),esc(c['platform'])) for c in sorted(CHECKS,key=lambda c:c['title'].casefold()))
    reports=''.join('<li><a href="%s">%s</a> · %s · %s</li>'%(esc(r['url']),esc(r['title']),esc(r['date']),esc(r['sector'])) for r in REPORTS)
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WACC · Framework coverage</title><style>%s table{border-collapse:collapse;width:100%%}td,th{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}li{margin:10px 0}.report{max-width:1200px;margin:24px auto;padding:0 20px}.scroll{overflow:auto}</style></head><body><header><h1>Framework coverage and technical checks</h1><nav><a href="/sources">Sources</a><a href="/library">Control workspace</a></nav></header><main class="report"><section class="box"><h2>Added source frameworks</h2><ul>%s</ul></section><section class="box"><h2>Cloud framework review</h2><p>SCF 2026.2 provides %d mapping columns and %d focal-document metadata rows across %d controls. The table counts SCF controls mapped to each source edition.</p><p>Priorities cover cloud and Microsoft 365.</p><div class="scroll"><table><thead><tr><th>Framework</th><th>Status</th><th>SCF controls mapped</th><th>Review and acquisition</th></tr></thead><tbody>%s</tbody></table></div></section><section class="box"><h2>Individual technical checks · %d</h2><ul>%s</ul></section><section class="box"><h2>WA audit context</h2><p>Reports are listed with their publication date and sector.</p><ul>%s</ul></section></main></body></html>'''%(STYLE,''.join(rows),review['mapping_columns'],review['focal_documents'],review['scf_controls'],priorities,len(CHECKS),checks,reports)
