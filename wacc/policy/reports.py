"""Framework alignment exports shared by the desktop and command line."""
from copy import deepcopy
import csv
import html
import io
import json
import os
from pathlib import Path
import re
import uuid

from . import alignment
from .contracts import PolicyError
from ..csv_safety import safe_cell


def model(state, full=True, framework_ids=None):
    original = state['run']
    selected = set(framework_ids) if framework_ids is not None else {f['id'] for f in original['versions']['frameworks']}
    if not selected or not selected <= {f['id'] for f in original['versions']['frameworks']}:
        raise PolicyError('Select frameworks that are included in this saved comparison.', 2)
    requirements = [r for r in original['requirements'] if r['frameworkId'] in selected]
    ids = {r['id'] for r in requirements}
    run = dict(original, requirements=requirements,
               versions=dict(original['versions'], frameworks=[f for f in original['versions']['frameworks'] if f['id'] in selected]),
               mappings=[m for m in original['mappings'] if m['source'] in ids and m['target'] in ids])
    results = alignment.for_run(original)
    rows = []
    for row in requirements:
        result = deepcopy(results[row['id']])
        if not full:
            result['matches'] = []
        rows.append(dict(id=row['id'], frameworkId=row['frameworkId'], officialReference=row['officialReference'],
                         heading=row['heading'], authoritativeText=row['authoritativeText'], context=row['context'],
                         sourceLocator=row['sourceLocator'], alignment=result))
    return dict(schemaVersion='1.0', reportType='FrameworkAlignment', name=run['name'], organisation=run.get('organisation', ''),
        scope=run['scope'], runId=run['runId'], analysisDate=run['createdAt'], versions=run['versions'],
        method=run['versions'].get('alignment', alignment.VERSION), description=alignment.DESCRIPTION,
        documents=[{k:v for k,v in d.items() if k not in ('passages', 'path')} for d in run['documents']],
        summary=alignment.summary(requirements, results), frameworkSummaries=alignment.framework_summaries(run, results),
        requirements=rows, mappings=run['mappings'], disclosure='FullPassages' if full else 'SummaryOnly',
        finalised=state['metadata'].get('selectedFinalised', state['metadata'].get('finalised', False)),
        limitations=['Some documents were not fully read or their text was not retained. Unmatched requirements cannot be treated as missing.']
            if any(not results[row['id']]['searchComplete'] for row in requirements) else [])


def location(match):
    return match['documentName'] + ' — ' + ', '.join(str(key) + ': ' + str(value) for key, value in match['locator'].items()
        if value is not None and key not in ('start', 'end', 'boundingBox'))


def render(state, format='json', full=True, framework_ids=None):
    data = model(state, full, framework_ids)
    if format == 'json':
        return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if format == 'html':
        return render_html(data)
    if format == 'csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['Comparison', 'Framework', 'Edition', 'Requirement', 'Framework text', 'Context', 'Status', 'Matching passages', 'Source locations', 'Match count', 'Search complete', 'Run', 'Method'])
        editions = {f['id']:f['edition'] for f in data['versions']['frameworks']}
        for row in data['requirements']:
            result = row['alignment']
            writer.writerow([safe_cell(value) for value in (data['name'], row['frameworkId'], editions[row['frameworkId']],
                row['id'], row['authoritativeText'], row['context'], result['status'],
                '\n\n'.join(m['excerpt'] for m in result['matches']), '\n'.join(location(m) for m in result['matches']),
                result['matchCount'], result['searchComplete'], data['runId'], data['method'])])
        return stream.getvalue()
    if format == 'markdown':
        def escape(value):
            return re.sub(r'([\\`*_{}\[\]()#+.!|>~-])', r'\\\1', html.escape(str(value)))
        lines = ['# ' + escape(data['name']), escape(data['description']), 'Scope: ' + escape(data['scope']['description'])]
        lines.extend(escape(value) for value in data['limitations'])
        for framework in data['frameworkSummaries']:
            lines += ['## ' + escape(framework['title']), escape(framework['edition']),
                      '; '.join(escape(status + ': ' + str(framework['counts'][status])) for status in alignment.STATUSES)]
            for row in data['requirements']:
                if row['frameworkId'] != framework['id']:
                    continue
                lines += ['### ' + escape(row['id'] + ' — ' + row['alignment']['status']), escape(row['context']), escape(row['authoritativeText'])]
                for match in row['alignment']['matches']:
                    lines += [escape(location(match)), escape(match['excerpt']), *(escape(c) for c in match['cautions'])]
        lines += ['Method: ' + escape(data['method']), 'Run: ' + escape(data['runId'])]
        return '\n\n'.join(lines)
    raise PolicyError('Unsupported report format.', 2)


def render_html(data):
    def esc(value):
        return html.escape(str(value if value is not None else ''))
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
        '<title>' + esc(data['name']) + '</title><style>',
        'body{font:16px/1.5 system-ui,sans-serif;color:#172c3b;background:#f3f6f8;margin:0}main{max-width:1100px;margin:auto;padding:32px}header,section{background:white;padding:24px;margin:0 0 24px;border:1px solid #d9e1e7;border-radius:8px}h1{font-size:30px}h2{font-size:22px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #d9e1e7}th{background:#edf3f7}p,blockquote,pre{white-space:pre-wrap;overflow-wrap:anywhere}blockquote{border-left:4px solid #487b9d;margin:16px 0;padding:12px 18px;background:#edf5fa}summary{cursor:pointer;padding:12px 0;font-weight:600}details{border-top:1px solid #d9e1e7;padding:4px 0}.muted{color:#526674}.scroll{overflow:auto}a{color:#205d84}@media print{body{background:white}main{padding:0}}',
        '</style></head><body><main><header><p>WACC · FRAMEWORK ALIGNMENT</p><h1>' + esc(data['name']) + '</h1>',
        '<p>' + esc(data['organisation']) + '</p><p>Scope: ' + esc(data['scope']['description']) + '</p>',
        '<p>' + esc(data['description']) + '</p><p class="muted">' + esc(data['analysisDate'][:10]) + ' · ' + esc(data['disclosure']) + '</p></header>',
        '<section><h2>Alignment by framework</h2><div class="scroll"><table><thead><tr><th>Framework</th><th>Requirements</th>' +
        ''.join('<th>' + esc(status) + '</th>' for status in alignment.STATUSES) + '</tr></thead><tbody>']
    for framework in data['frameworkSummaries']:
        out.append('<tr><td><a href="#' + esc(framework['id']) + '">' + esc(framework['title']) + '</a></td><td>' + str(framework['requirements']) + '</td>' +
                   ''.join('<td>' + str(framework['counts'][status]) + '</td>' for status in alignment.STATUSES) + '</tr>')
    out.append('</tbody></table></div>' + ''.join('<p>' + esc(value) + '</p>' for value in data['limitations']) + '</section>')
    out.append('<section><h2>Documents</h2>' + ''.join('<p>' + esc(d['name'] + ' — ' + d['status']) + '</p>' for d in data['documents']))
    if data['scope'].get('skippedInputs'):
        out.append('<details><summary>Files skipped (unsupported format)</summary><pre>' + esc('\n'.join(data['scope']['skippedInputs'])) + '</pre></details>')
    out.append('</section>')
    for framework in data['frameworkSummaries']:
        out.append('<section id="' + esc(framework['id']) + '"><h2>' + esc(framework['title']) + '</h2><p>' + esc(framework['edition']) + '</p>')
        for status in alignment.STATUSES:
            rows = [r for r in data['requirements'] if r['frameworkId'] == framework['id'] and r['alignment']['status'] == status]
            if not rows:
                continue
            out.append('<h3>' + esc(status) + ' (' + str(len(rows)) + ')</h3>')
            for row in rows:
                result = row['alignment']
                out.append('<details><summary>' + esc(row['officialReference'] + ' — ' + row['heading']) + '</summary><p>' + esc(row['context']) + '</p><p>' + esc(row['authoritativeText']) + '</p>')
                for match in result['matches']:
                    out.append('<p><strong>' + esc(location(match)) + '</strong></p><blockquote>' + esc(match['excerpt']) + '</blockquote>' +
                        ''.join('<p>' + esc(c) + '</p>' for c in match['cautions']))
                if result['matchCount'] > len(result['matches']):
                    out.append('<p>' + str(result['matchCount']) + ' matching passages; ' + str(len(result['matches'])) + ' shown.</p>')
                out.append('</details>')
        out.append('</section>')
    out.append('<section><details><summary>Source versions and framework relationships</summary><p>Run: ' + esc(data['runId']) + '</p><p>Method: ' + esc(data['method']) + '</p><pre>' +
               esc(json.dumps(dict(versions=data['versions'], mappings=data['mappings']), ensure_ascii=False, indent=2)) + '</pre></details></section></main></body></html>')
    return ''.join(out)


def write_output(path, content, force=False):
    path = Path(path)
    if path.exists() and not force:
        raise PolicyError("Output already exists; use --force to replace it.", 6)
    stage = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with stage.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(stage, path)
    except OSError:
        raise PolicyError("Could not save output. The previous file has been preserved.", 6)
    finally:
        if stage.exists():
            stage.unlink()


def export_report(state, path, format, full=True, force=False, assessment_path=None, framework_ids=None):
    protected={Path(d['path']).resolve() for d in state['run']['documents']}
    if assessment_path:
        protected.add(Path(assessment_path).resolve())
    if Path(path).resolve() in protected:
        raise PolicyError('Choose a report filename different from the assessment and original documents.',6)
    write_output(path,render(state,format,full,framework_ids),force)
