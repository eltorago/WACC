"""Display publisher implementation context with its original edition."""
import html
from urllib.parse import urlencode
from .framework_families import strategy_uid


def render(control):
    esc=html.escape
    attributes=control.attributes
    result=''
    broader=strategy_uid(control.uid)
    if broader:
        result+='<p>Essential Eight maturity detail · <a href="/?%s">View the broader ACSC strategy (2017)</a></p>'%esc(urlencode({'q':broader,'view':'cards'}))
    if attributes.get('edition_note'):
        result+='<p class="muted"><strong>Source edition:</strong> %s</p>'%esc(attributes['edition_note'])
    if attributes.get('identifier_note'):
        result+='<p class="muted">%s</p>'%esc(attributes['identifier_note'])
    if attributes.get('scope_note'):
        result+='<p class="muted">%s</p>'%esc(attributes['scope_note'])
    if attributes.get('legal_context'):
        result+='<p>'+' · '.join('<a href="/?%s">%s</a>' % (
            esc(urlencode({'q':ref['uid'],'view':'cards'})),esc(ref['label']))
            for ref in attributes['legal_context'])+'</p>'
    if attributes.get('implementation_examples'):
        text=attributes['implementation_examples']
        url=attributes.get('implementation_source_url') or attributes.get('source_url')
        link='<p><a href="%s">Read the publisher guidance</a></p>'%esc(url) if url else ''
        result+='<details><summary>Publisher implementation guidance</summary><p class="source-text" style="white-space:pre-wrap">%s</p>%s</details>'%(esc(text),link)
    return result
