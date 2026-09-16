"""Local source status and a single background acquisition job."""
from collections import Counter
import html
import secrets
from threading import Lock, Thread

from . import sources


class AcquisitionJob:
    def __init__(self, reload_corpus):
        self.token = secrets.token_urlsafe(32)
        self.lock = Lock()
        self.running = False
        self.rows = []
        self.message = ''
        self.reload_corpus = reload_corpus

    def snapshot(self):
        with self.lock:
            return self.running, list(self.rows), self.message

    def start(self, token):
        if not token.isascii() or not secrets.compare_digest(token, self.token):
            return False
        with self.lock:
            if self.running:
                return True
            self.running = True
            self.rows = []
            self.message = 'Checking existing files and downloading missing public sources…'
        Thread(target=self.run, daemon=True).start()
        return True

    def run(self):
        def progress(row):
            with self.lock:
                self.rows.append(row)
        try:
            sources.acquire(progress=progress)
            with self.lock:
                self.message = 'Downloads finished. Reloading the corpus…'
            self.reload_corpus()
            with self.lock:
                self.message = 'Finished. The corpus has been reloaded. Review any manual or failed items below.'
        except Exception as error:
            with self.lock:
                self.message = 'Acquisition or reload failed: %s. Existing corpus remains available.' % error
        finally:
            with self.lock:
                self.running = False


def render(job):
    from .control_workspace import STYLE
    esc = html.escape
    running, results, message = job.snapshot()
    rows = sources.status()
    counts = Counter(row['state'] for row in rows)
    automatic = sum(row['method'] == 'automatic' for row in rows)
    latest = {name: (state, detail) for name, state, detail in results}
    items = []
    for row in sorted(rows, key=lambda r: (r['state'] == 'available', r['filename'].casefold())):
        name = row['filename']
        state, detail = latest.get(name, (row['state'], ''))
        links = ' · '.join('<a href="%s">Publisher download %d</a>' % (esc(url), i + 1)
                           for i, url in enumerate(row['urls']))
        instructions = row['instructions'] or 'Download automatically. If publisher bytes change, review the new edition before replacing the reviewed source.'
        items.append('<tr><td>%s</td><td>%s<br><small>%s</small></td><td>%s<p>%s</p><small>%s</small></td></tr>' %
                     (esc(name), esc(row['state']), esc(row['method']), links, esc(instructions), esc((state + ': ' + detail) if detail else '')))
    refresh = '<meta http-equiv="refresh" content="4">' if running else ''
    return '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">%s
<title>WACC · Sources</title><style>%s .source-page{max-width:1200px;margin:24px auto;padding:0 20px}table{width:100%%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}td:first-child{width:30%%}.scroll{overflow:auto}code{overflow-wrap:anywhere}</style></head>
<body><header><h1>Frameworks and source documents</h1><nav><a href="/library">Control workspace</a><a href="/frameworks">Framework coverage</a></nav></header>
<main class="source-page"><section class="box"><h2>Acquire sources</h2><p>%d of %d documents have automatic acquisition configured. %d reviewed files are available, %d are missing and %d have changed.</p>
<p>Download public sources from their publishers, keep matching files, and reload the corpus when finished. Files stay on this computer. An automatic route can still be blocked by a publisher or require an edition review.</p>
<form method="post" action="/sources/acquire"><input type="hidden" name="token" value="%s"><button %s>Download missing public sources and reload</button></form><p role="status">%s</p>
<p>Using source folder: <code>%s</code></p></section>
<section class="box"><h2>Import files downloaded manually</h2><p>Download sign-in or export-only documents using the instructions below. Then run this from the repository folder, replacing the folder with your download location:</p><pre><code>python -m wacc sources --import-from "C:\\path\\to\\downloads"</code></pre>
<p>WACC recognises reviewed files by their contents and copies them under the expected names. It does not move originals or import unmatched files. Restart the server afterwards, or use the button above to reload.</p>
<p>For a check without downloads: <code>python -m wacc sources --status</code>. A missing source document does not necessarily mean its curated corpus extract is unavailable. Acquiring a PDF does not automatically create new structured controls.</p></section>
<section class="box"><h2>Source status</h2><div class="scroll"><table><thead><tr><th>Document</th><th>Local status / acquisition</th><th>Next step and last result</th></tr></thead><tbody>%s</tbody></table></div></section></main></body></html>''' % (
        refresh, STYLE, automatic, len(rows), counts['available'], counts['missing'], counts['changed'],
        esc(job.token), 'disabled' if running else '', esc((message + ' %d of %d documents checked.' % (len(results), len(rows))) if running else message or 'Ready to acquire sources.'),
        esc(str(sources.source_directory())), ''.join(items))
