"""Shared offline exports. Report content is text, never executable markup."""
import csv
import html
import io
import json
import os
from pathlib import Path
import uuid

from .contracts import PolicyError
from .service import apply_reviews, summary, framework_summaries


def model(state, full=True, framework_ids=None):
    run = state["run"]
    if framework_ids is not None:
        selected = set(framework_ids)
        if not selected or not selected <= {f['id'] for f in run['versions']['frameworks']}:
            raise PolicyError('Select frameworks that are included in this saved assessment.', 2)
        rows = [r for r in run['requirements'] if r['frameworkId'] in selected]
        ids = {r['id'] for r in rows}
        run = dict(run, requirements=rows,
                   versions=dict(run['versions'], frameworks=[f for f in run['versions']['frameworks'] if f['id'] in selected]),
                   mappings=[m for m in run['mappings'] if m['source'] in ids and m['target'] in ids])
    rows = apply_reviews(run, state["events"])
    if not full:
        for row in rows:
            row["evidence"] = []
            if "review" in row:
                row["review"].pop("comment", None)
                row['review'].pop('manualEvidence', None)
                row['review'].pop('reason', None)
    return dict(schemaVersion="1.0", name=run["name"], organisation=run.get("organisation", ""),
                scope=run["scope"], runId=run["runId"], analysisDate=run["createdAt"], versions=run["versions"],
                documents=[{k: v for k, v in d.items() if k not in ("passages", "path")} for d in run["documents"]],
                summary=summary(run, state["events"]), frameworkSummaries=framework_summaries(run, state['events']),
                requirements=rows, mappings=run["mappings"],
                finalised=state["metadata"].get("selectedFinalised", state['metadata'].get('finalised',False)), disclosure="FullEvidence" if full else "SummaryOnly",
                limitations=run["limitations"], purpose="Documented policy coverage; implementation and operating effectiveness are not assessed.")


def safe_cell(value):
    text = str(value if value is not None else "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def render(state, format="json", full=True, framework_ids=None):
    data = model(state, full, framework_ids)
    if format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    if format == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["Assessment", "Scope", "Run", "Framework edition", "Requirement", "Automated", "Review state", "Reviewer finding", "Missing obligations", "Evidence", "Limitations", "Corpus version", "Engine version", "Requirements in scope", "Computable requirements", "Excluded requirements", "Reviewed requirements", "Framework", "Framework requirements in scope", "Framework reviewed", "Framework confirmed coverage percent", "Framework automatically assessed", "Manual evidence"])
        framework_counts = {f['id']:f for f in data['frameworkSummaries']}
        for r in data["requirements"]:
            edition = next(f["edition"] for f in data["versions"]["frameworks"] if f["id"] == r["frameworkId"])
            counts = framework_counts[r['frameworkId']]
            writer.writerow([safe_cell(v) for v in [data["name"], data["scope"]["description"], data["runId"], edition,
                r["id"], r["automatedFinding"], r["reviewState"], r["reviewerFinding"], "; ".join(r["missingObligations"]),
                "\n".join(e["excerpt"] + " " + json.dumps(e["locator"]) for e in r["evidence"]),
                "; ".join(data["limitations"] + r["flags"]), data['versions']['corpus'],data['versions']['engine'],
                data['summary']['inScope'],data['summary']['computable'],data['summary']['excluded'],data['summary']['reviewed'],
                r['frameworkId'], counts['inScope'],counts['reviewed'],counts['confirmedEvidenceFloor']['percent'],counts['computable'],
                '\n'.join(e['excerpt'] + ' ' + json.dumps(e['locator']) for e in r.get('review',{}).get('manualEvidence',[])) ]])
        return stream.getvalue()
    lines = [data["name"], "PILOT — " + ("Finalised snapshot" if data["finalised"] else "Incomplete review / working assessment"),
             "Scope: " + data["scope"]["description"] + " (" + data["scope"]["mode"] + ")",
             "Run: " + data["runId"] + " | " + data["analysisDate"], data["purpose"],
             "Versions: " + json.dumps(data["versions"], ensure_ascii=False),
             "Counts and denominators: " + json.dumps(data["summary"], ensure_ascii=False),
             "Documents: " + json.dumps(data["documents"], ensure_ascii=False), *data["limitations"]]
    lines += ['', 'Coverage by framework']
    for f in data['frameworkSummaries']:
        lines += [f['title'] + ' — ' + f['edition'],
                  'In scope: %d; reviewed: %d / %d; confirmed coverage: %s; automatically assessed: %d / %d' %
                  (f['inScope'], f['reviewed'], f['reviewable'], percentage(f['confirmedEvidenceFloor']), f['computable'], f['inScope']),
                  'Reviewer findings: ' + json.dumps(f['reviewerCounts'])]
    for row in data["requirements"]:
        lines += ["", row["id"] + " — " + row["heading"], row["context"], row["authoritativeText"],
                  "Automated: " + row["automatedFinding"] + "; review: " + row["reviewState"] + "; reviewer finding: " + str(row["reviewerFinding"]),
                  "Missing obligations: " + ", ".join(row["missingObligations"])]
        if row.get("review"):
            lines.append("Review: " + json.dumps(row["review"], ensure_ascii=False))
        for e in row["evidence"]:
            lines += ["Evidence (" + e["state"] + "): " + e["excerpt"], "Source: " + e["documentId"] + " " + json.dumps(e["locator"]),
                      "Rule " + e["ruleVersion"] + ": " + json.dumps(e["checks"], ensure_ascii=False)]
    lines += ["", "Framework relationships (mapped only; no transfer of coverage): " + json.dumps(data["mappings"], ensure_ascii=False)]
    if format == "markdown":
        # Escape Markdown control characters, raw HTML and autolinks from documents.
        import re
        return "\n\n".join(re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(line)) for line in lines)
    if format == "html":
        return render_html(data)
    raise PolicyError("Unsupported report format.", 2)


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


def percentage(metric):
    if metric['percent'] is None:
        return 'N/A'
    return '%.1f%% (%s / %d)' % (metric['percent'], format(metric['numerator'], '.2f').rstrip('0').rstrip('.'), metric['denominator'])


def render_html(data):
    esc = lambda value: html.escape(str(value if value is not None else ''))
    labels = {'FullCandidate':'Full evidence candidate', 'PartialCandidate':'Partial evidence candidate',
              'NoEvidenceFound':'No qualifying evidence found', 'Ambiguous':'Needs closer review', 'NotAssessed':'Not assessed',
              'Covered':'Covered', 'PartiallyCovered':'Partially covered', 'NotCovered':'Not covered', 'NotApplicable':'Not applicable'}
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
           '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">',
           '<title>' + esc(data['name']) + '</title><style>',
           'body{font:16px/1.5 system-ui,sans-serif;color:#172c3b;background:#f3f6f8;margin:0}main{max-width:1100px;margin:auto;padding:32px}header,section{background:white;padding:24px;margin:0 0 24px;border:1px solid #d9e1e7;border-radius:8px}h1{font-size:30px;margin:8px 0}h2{font-size:22px}h3{font-size:18px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d9e1e7}th{background:#edf3f7}p,blockquote,pre{overflow-wrap:anywhere;white-space:pre-wrap}pre{white-space:pre-wrap;font-size:12px}blockquote{border-left:4px solid #487b9d;margin:16px 0;padding:12px 18px;background:#edf5fa}summary{cursor:pointer;padding:12px 0;font-weight:600}.muted{color:#526674}.tag{display:inline-block;font-size:12px;font-weight:700;letter-spacing:1px;color:#24516d}.scroll{overflow:auto}details{border-top:1px solid #d9e1e7;padding:4px 0}a{color:#205d84}.meter{height:8px;background:#e1e8ed;margin-top:6px}.fill{height:100%;background:#267756}@media print{body{background:white}main{padding:0}section,header{break-inside:avoid}details{break-inside:avoid}}',
           '</style></head><body><main><header><span class="tag">WACC · POLICY COVERAGE · PILOT</span>',
           '<h1>' + esc(data['name']) + '</h1><p>' + esc(data['organisation']) + '</p>',
           '<p><strong>Scope:</strong> ' + esc(data['scope']['description']) + '</p>',
           '<p class="muted">' + esc('Finalised snapshot' if data['finalised'] else 'Working assessment') +
           ' · ' + esc(data['analysisDate'][:10]) + ' · ' + esc(data['disclosure']) + '</p>',
           '<p>' + esc(data['purpose']) + '</p></header><section><h2>Coverage by framework</h2>',
           '<p>Confirmed coverage uses the points supported by reviewer-accepted evidence. Unreviewed requirements remain in the denominator; exclusions are shown separately. Automatic checks have their own counts.</p>',
           '<div class="scroll"><table><thead><tr><th>Framework</th><th>In scope</th><th>Reviewed</th><th>Confirmed coverage</th><th>Automatically assessed</th><th>Excluded</th></tr></thead><tbody>']
    for f in data['frameworkSummaries']:
        metric = f['confirmedEvidenceFloor']
        out.append('<tr><td><a href="#framework-' + esc(f['id']) + '">' + esc(f['title']) + '</a><br><span class="muted">' + esc(f['edition']) + '</span></td><td>' + str(f['inScope']) + '</td><td>' + str(f['reviewed']) + ' / ' + str(f['reviewable']) + '</td><td>' + esc(percentage(metric)) + '<div class="meter"><div class="fill" style="width:' + str(metric['percent'] or 0) + '%"></div></div></td><td>' + str(f['computable']) + ' / ' + str(f['inScope']) + '</td><td>' + str(f['excluded']) + '</td></tr>')
    out += ['</tbody></table></div><h3>Review status</h3><div class="scroll"><table><thead><tr><th>Framework</th><th>Covered</th><th>Partial</th><th>Not covered</th><th>Reviewed but not assessed</th><th>Awaiting review</th></tr></thead><tbody>']
    for f in data['frameworkSummaries']:
        counts = f['reviewerCounts']
        out.append('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in [f['id'], counts['Covered'], counts['PartiallyCovered'], counts['NotCovered'], counts['NotAssessed'], f['reviewable']-f['reviewed']]) + '</tr>')
    out += ['</tbody></table></div><h3>Current limits</h3>' + ''.join('<p>' + esc(v) + '</p>' for v in data['limitations']),
            '</section><section><h2>Documents</h2><div class="scroll"><table><thead><tr><th>Document</th><th>Import</th><th>Approval</th></tr></thead><tbody>']
    for d in data['documents']:
        out.append('<tr>' + ''.join('<td>' + esc(v) + '</td>' for v in [d['name'], d['status'], d['approvalStatus']]) + '</tr>')
    out += ['</tbody></table></div></section>']
    for f in data['frameworkSummaries']:
        out.append('<section id="framework-' + esc(f['id']) + '"><h2>' + esc(f['title']) + '</h2><p>' + esc(f['edition']) + '</p>')
        for row in data['requirements']:
            if row['frameworkId'] != f['id']:
                continue
            finding = labels.get(row['reviewerFinding'], 'Awaiting review')
            out.append('<details id="' + esc(row['id']) + '"><summary>' + esc(row['officialReference'] + ' — ' + row['heading'] + ' · ' + finding) + '</summary><p>' + esc(row['context']) + '</p><p>' + esc(row['authoritativeText']) + '</p><p><strong>Automatic result:</strong> ' + esc(labels[row['automatedFinding']]) + '</p>')
            out.append('<p><strong>Points without automatic evidence:</strong> ' + esc(', '.join(row['missingObligations']) or 'None') + '</p>')
            if row.get('review'):
                review = row['review']
                out.append('<p><strong>Reviewer:</strong> ' + esc(review['reviewer']) + ' · ' + esc(finding) + '</p>')
                for name in ('reason', 'comment'):
                    if review.get(name): out.append('<p>' + esc(review[name]) + '</p>')
            for e in row['evidence'] + row.get('review', {}).get('manualEvidence', []):
                out.append('<blockquote>' + esc(e['excerpt']) + '</blockquote><p class="muted">Source ' + esc(e['documentId']) + ' · ' + esc(json.dumps(e['locator'], ensure_ascii=False)) + '</p>')
                if e.get('checks'):
                    out.append('<details><summary>Recorded rule checks</summary><pre>' + esc(json.dumps(e['checks'], ensure_ascii=False, indent=2)) + '</pre></details>')
            out.append('</details>')
        out.append('</section>')
    out.append('<section><details><summary>Versions, source fingerprints and framework relationships</summary><p>Run: ' + esc(data['runId']) + '</p><pre>' + esc(json.dumps(dict(versions=data['versions'], documents=data['documents'], summary=data['summary'], mappings=data['mappings']), ensure_ascii=False, indent=2)) + '</pre></details></section></main></body></html>')
    return ''.join(out)
