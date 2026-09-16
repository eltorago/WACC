"""Explicit local ATT&CK assessments for the practical control library.

MITRE owns the technique taxonomy and mitigation relationships. WACC owns the
control-to-technique judgements and explanations, including the decisions that
some administrative controls have no direct technique mapping.
"""
import html
import json
from pathlib import Path


DATA = json.loads((Path(__file__).resolve().parents[1] / 'data/workspace-attack.json').read_text(encoding='utf-8'))
ASSESSMENTS = DATA['controls']
EFFECTS = {
    'Prevent': 'Reduces likelihood',
    'Detect': 'Supports detection',
    'Respond': 'Contains the attack',
    'Recover': 'Limits impact / recovery',
    'Support': 'Enables other safeguards',
}


def search_text(control_id, corpus=None):
    """Search local explanations and IDs, plus publisher names when loaded."""
    assessment = ASSESSMENTS.get(control_id, {})
    parts = [json.dumps(assessment, ensure_ascii=False)]
    if corpus is not None:
        for connection in assessment.get('connections', []):
            technique = corpus.techniques.get(connection['technique'])
            mitigation = corpus.mitigations.get(connection.get('mitigation'))
            if technique:
                parts.extend([technique.name, ' '.join(technique.tactics)])
            if mitigation:
                parts.append(mitigation.name)
    return ' '.join(parts)


def matches_identifiers(control_id, identifiers):
    """A sub-technique ID must match intact; parent IDs also find their children."""
    connections = ASSESSMENTS.get(control_id, {}).get('connections', [])
    keys = {c['technique'] for c in connections} | {c['mitigation'] for c in connections if 'mitigation' in c}
    return all(any(key == identifier.upper() or key.startswith(identifier.upper() + '.')
                   for key in keys) for identifier in identifiers)


def connection_status(connection, corpus):
    """Never describe a missing or changed publisher relationship as verified."""
    if connection['technique'] not in corpus.techniques:
        return 'Technique unavailable in the loaded ATT&CK source.'
    mitigation = connection.get('mitigation')
    if mitigation and (
        mitigation not in corpus.mitigations or not any(
            edge.mitigation_key == mitigation and edge.technique_key == connection['technique']
            for edge in corpus.mitigates
        )
    ):
        return 'MITRE mitigation relationship needs review against the loaded source.'
    return ''


def render(control_id, corpus):
    esc = html.escape
    assessment = ASSESSMENTS.get(control_id)
    out = ['<section class="box" id="attack"><h3>MITRE ATT&amp;CK</h3>']
    if assessment is None:
        out.append('<p>ATT&amp;CK assessment has not yet been completed for this control.</p>')
    else:
        out.append('<p class="muted">These are local WACC assessments of how the control helps. '
                   'MITRE publishes the technique and mitigation references; these links do not establish coverage.</p>')
        if assessment.get('note'):
            out.append('<p><span class="badge">No direct technique mapping</span></p><p>%s</p>' % esc(assessment['note']))
        connections = assessment['connections']
        if connections and not corpus.techniques:
            out.append('<p role="status">The ATT&amp;CK source is not loaded. Run '
                       '<code>python -m wacc sources</code> and restart WACC to load technique names '
                       'and check the publisher relationships.</p>')
        for connection in connections:
            key = connection['technique']
            technique = corpus.techniques.get(key)
            status = connection_status(connection, corpus)
            technique_url = 'https://attack.mitre.org/techniques/%s/' % key.replace('.', '/')
            label = key + (' — ' + technique.name if technique else '')
            out.append('<div class="attack-connection"><h4><a href="%s">%s</a></h4>' % (esc(technique_url), esc(label)))
            out.append('<span class="badge">%s</span>' % esc(EFFECTS[connection['effect']]))
            if technique and technique.tactics:
                out.append('<p class="muted">Tactics: %s</p>' % esc(' · '.join(technique.tactics)))
            out.append('<p>%s</p>' % esc(connection['how']))
            mitigation_key = connection.get('mitigation')
            if status:
                out.append('<p class="muted">%s Local explanation shown pending source verification.</p>' % esc(status))
            elif mitigation_key:
                mitigation = corpus.mitigations[mitigation_key]
                out.append('<p class="muted">MITRE mitigation reference: '
                           '<a href="https://attack.mitre.org/mitigations/%s/">%s — %s</a></p>'
                           % (esc(mitigation_key), esc(mitigation_key), esc(mitigation.name)))
            out.append('</div>')
        source = corpus.threat_sources.get('attack-enterprise')
        out.append('<small>Enterprise ATT&amp;CK · mappings reviewed against %s%s. '
                   'Mobile and ICS techniques are outside this mapping.</small>'
                   % (esc(DATA['reviewed_version']), (' · loaded source ' + esc(source.version))
                      if source and source.version != DATA['reviewed_version'] else ''))
        if source and source.version != DATA['reviewed_version']:
            out.append('<p role="status">The loaded ATT&amp;CK edition differs from the mapping review edition. '
                       'Recheck these assessments before relying on them.</p>')
    out.append('</section>')
    return ''.join(out)
