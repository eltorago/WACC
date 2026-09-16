"""Dated WA audit observations, linked independently of current requirements."""
import html
import json
from pathlib import Path

DATA = json.loads((Path(__file__).resolve().parents[1] / 'data/wa-audit-context.json').read_text(encoding='utf-8'))
REPORTS = DATA['reports']
for report in REPORTS:
    report['url'] = 'https://audit.wa.gov.au/reports-and-publications/reports/' + report['slug'] + '/'


def for_control(control_id):
    return [r for r in REPORTS if control_id in r['controls']]


def render(control_id):
    reports = for_control(control_id)
    if not reports:
        return ''
    esc = html.escape
    return '<section class="box" id="wa-context"><h3>WA audit context</h3><p class="muted">%s</p>%s</section>' % (
        esc(DATA['notice']), ''.join(
            '<details><summary>%s · %s</summary><p class="muted">%s</p><p>%s</p><p><strong>Assessment application:</strong> %s</p><a href="%s">Read the OAG report</a></details>' %
            (esc(r['title']),esc(r['date']),esc(r['sector']),esc(r['finding']),esc(r['assessment']),esc(r['url'])) for r in reports))
