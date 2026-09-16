"""Specific documentary evidence, checked against published corpus procedures."""
import html
import json
from pathlib import Path
from urllib.parse import urlencode

EVIDENCE=json.loads((Path(__file__).resolve().parents[1]/'data/workspace-grc-evidence.json').read_text(encoding='utf-8'))


def render(control_id, corpus, selected):
    evidence=EVIDENCE[control_id]
    uid=evidence['source_uid']
    if uid.split(':')[0] not in selected:
        return ''
    esc=html.escape
    statement=next((s for s in corpus.statements_for(uid) if s.is_published and s.published_ref==evidence['published_ref']),None)
    verified=statement is not None and all(d.casefold() in statement.text.casefold() for d in evidence['documents'])
    status='Document names checked against the loaded publisher procedure.' if verified else 'Publisher procedure is not loaded or has changed; the document match needs revalidation.'
    source=corpus.control(uid)
    label=evidence['publisher']+' · '+(source.identifier if source else uid)+' · Examine'
    link='<a href="/?%s">%s</a>'%(esc(urlencode({'q':uid,'view':'cards'})),esc(label)) if source else esc(label)
    return '<div class="grc-evidence"><h4>Documents to examine</h4><p>%s</p><ul>%s</ul><h4>What to verify in these documents</h4><p>%s</p><p class="muted">%s %s</p></div>'%(
        link,''.join('<li>%s</li>'%esc(d) for d in evidence['documents']),esc(evidence['application']),esc(status),esc(evidence['support']))
