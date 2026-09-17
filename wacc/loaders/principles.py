"""Expose ASD's ISM principles separately without duplicating source records."""
from ..model import Fidelity

# Publisher order in the reviewed September 2026 edition; numbering has gaps.
FUNCTIONS = {
    'Govern': ('GOV', (1, 8, 2, 4, 9, 3, 5, 6, 10, 11, 12, 13, 14, 7)),
    'Identify': ('IDE', (1, 5, 2, 3, 6, 4)),
    'Protect': ('PRO', (1, 16, 13, 12, 5, 4, 6, 7, 8, 17, 10, 18, 19, 20, 9, 14, 15)),
    'Detect': ('DET', (1, 4, 2, 3, 5)),
    'Respond': ('RES', (1, 5, 3, 2, 4)),
    'Recover': ('REC', (2, 1)),
}
IDENTIFIERS = {f'{prefix}-{number:02}': function
               for function, (prefix, numbers) in FUNCTIONS.items() for number in numbers}


def partition(corpus, framework):
    """Move the publisher-labelled ISM-principle class into its outcome framework.

    The official OSCAL download already contains the full statements, applicability
    and stable labels. Legacy ISM UIDs remain resolvable, but are not extra records.
    """
    records = [c for c in corpus.controls_for('ism') if c.attributes.get('class') == 'ISM-principle']
    if {c.identifier for c in records} != set(IDENTIFIERS) or len(records) != len(IDENTIFIERS):
        raise ValueError('Expected the 49 reviewed September 2026 ASD cyber security principles; review the source edition.')
    if any(not c.text.strip() or not c.title for c in records):
        raise ValueError('An ASD cyber security principle has no title or statement.')
    for c in records:
        old_uid = c.uid
        del corpus.controls[old_uid]
        c.framework_key = framework.key
        c.depth = 0
        c.fidelity = Fidelity.OFFICIAL_MACHINE_READABLE
        c.attributes.update(source_url=framework.source_url, source_framework='ism',
                            legacy_uid=old_uid, function=IDENTIFIERS[c.identifier])
        corpus.add_control(c)
        corpus.control_aliases[old_uid] = c.uid
    return {'controls': len(records), 'functions': len(FUNCTIONS)}
