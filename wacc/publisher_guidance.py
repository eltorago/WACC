"""Display publisher implementation context with its original edition."""
import html


def render(control):
    esc=html.escape
    attributes=control.attributes
    result=''
    if attributes.get('edition_note'):
        result+='<p class="muted"><strong>Source edition:</strong> %s</p>'%esc(attributes['edition_note'])
    if attributes.get('identifier_note'):
        result+='<p class="muted">%s</p>'%esc(attributes['identifier_note'])
    if attributes.get('implementation_examples'):
        text=attributes['implementation_examples']
        url=attributes.get('implementation_source_url') or attributes.get('source_url')
        link='<p><a href="%s">Read the publisher guidance</a></p>'%esc(url) if url else ''
        result+='<details><summary>Publisher implementation guidance</summary><p class="source-text" style="white-space:pre-wrap">%s</p>%s</details>'%(esc(text),link)
    return result
