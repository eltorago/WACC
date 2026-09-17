"""Import the reviewed WA PRIS consolidation, retaining complete legal provisions.

WA uses different Word styles from Commonwealth legislation. Sections stay whole so
conditions, exceptions and definitions remain with the provision they qualify. Each
numbered IPP subclause is searchable; unnumbered principles remain whole. Editorial
notes, the contents and amendment insertions never become separate requirements.
"""
import hashlib
import re
from pathlib import Path

from ..io.docx import Document, Paragraph, Table
from ..model import Control, ObligationStrength, Origin, Provenance
from .legislation import obligation_of

SOURCE_FILE = 'wa-pris-act-2026-07.docx'
SOURCE_URL = 'https://www.legislation.wa.gov.au/legislation/statutes.nsf/RedirectURL?OpenAgent=&query=mrdoc_49691.docx'
PAGE_URL = 'https://www.legislation.wa.gov.au/legislation/statutes.nsf/law_a147470.html'
REVIEWED_SHA256 = 'e8354bcce6be68901e64101aabca8809906fd1d9f73dd7d95ee3e02a8223d4d7'
EDITION = '00-g0-01 (1 July 2026)'
UNCOMMENCED_SECTIONS = set(range(57, 76)) | set(range(118, 122)) | set(range(134, 137)) | set(range(191, 196))
SECTION_NUMBERS = set(range(1, 248)) - UNCOMMENCED_SECTIONS - {230, 231}


def load_into(corpus, framework, path):
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != REVIEWED_SHA256:
        raise ValueError('WA PRIS source differs from the reviewed July 2026 consolidation; review before importing.')
    records = []
    parents = {}
    current = None
    schedule = None
    principle = None
    section_numbers = set()
    principle_numbers = {1: set(), 2: set()}

    def add(identifier, title, depth, parent=None, structural=False, **attributes):
        record = Control(framework_key=framework.key, identifier=identifier, title=title,
                         text='', depth=depth, parent_uid=parent.uid if parent else None,
                         section_ref=title, origin=Origin.GENERATED,
                         obligation=ObligationStrength.INFORMATIVE,
                         obligation_provenance=Provenance.DERIVED,
                         attributes={'structural': structural, 'edition': EDITION,
                                     'source_url': PAGE_URL, **attributes})
        records.append(record)
        return record

    for block in Document(str(path)).blocks():
        if isinstance(block, Table):
            if current is not None:
                current.text += '\n' + '\n'.join(' | '.join(row) for row in block.rows)
            continue
        if not isinstance(block, Paragraph) or not block.text:
            continue
        style, text = block.style, block.text
        if style == 'nHeading 2':
            break  # Compilation notes and the defined-terms index are not provisions.
        if style in ('heading 2', 'heading 3', 'heading 4'):
            depth = int(style[-1]) - 2
            number, title = text.split(' — ', 1)
            parent = parents.get(depth - 1)
            identifier = (parent.identifier + ' ' if parent else '') + number
            parents = {d: p for d, p in parents.items() if d < depth}
            parents[depth] = add(identifier, title, depth, parent, structural=True)
            current = None
        elif style == 'heading 5':
            match = re.fullmatch(r'(\d+)\.\s+(.+)', text)
            if not match:
                raise ValueError('Unrecognised WA PRIS section heading: ' + text)
            number = int(match[1])
            section_numbers.add(number)
            parent = parents[max(parents)]
            current = add('s ' + str(number), match[2], parent.depth + 1, parent, section=number)
        elif style == 'yScheduleHeading':
            match = re.fullmatch(r'Schedule ([12]) — (.+)', text)
            if not match:
                raise ValueError('Unrecognised WA PRIS schedule: ' + text)
            schedule = int(match[1])
            parents = {0: add('Schedule ' + match[1], match[2], 0, structural=True)}
            current = None
        elif style == 'yHeading 5':
            match = re.fullmatch(r'(\d+)\. Principle \d+: (.+)', text)
            if not match or schedule is None:
                raise ValueError('Unrecognised WA PRIS principle: ' + text)
            number = int(match[1])
            principle_numbers[schedule].add(number)
            prefix = 'IPP ' if schedule == 1 else 'RSP '
            principle = add(prefix + str(number), match[2], 1, parents[0],
                            structural=True, schedule=schedule, principle=number)
            current = principle
        elif style == 'ySubsection':
            match = re.match(r'(\d+\.\d+)\s+(.+)', text)
            if match:
                prefix = 'IPP ' if schedule == 1 else 'RSP '
                if int(match[1].split('.')[0]) != principle.attributes['principle']:
                    raise ValueError('WA PRIS subclause is outside its principle: ' + text)
                current = add(prefix + match[1], principle.title, 2, principle,
                              schedule=schedule, principle=principle.attributes['principle'])
                current.text = match[2]
            else:
                current = principle
                current.attributes['structural'] = False
                current.text = text
        elif current is not None and style not in ('yShoulderClause', 'CentredBaseLine'):
            if style.startswith(('Ednote', 'Footnote')):
                current.attributes.setdefault('editorial_notes', []).append(text)
            else:
                current.text = (current.text + '\n' + text).strip()

    if section_numbers != SECTION_NUMBERS or principle_numbers != {1: set(range(1, 12)), 2: set(range(1, 6))}:
        raise ValueError('Incomplete WA PRIS sections or principles; corpus was not changed.')
    if len({c.uid for c in records}) != len(records):
        raise ValueError('Duplicate WA PRIS identifiers; corpus was not changed.')
    if any(not c.text and not c.attributes['structural'] for c in records):
        raise ValueError('Empty WA PRIS provision; corpus was not changed.')
    for record in records:
        if record.text:
            record.obligation = obligation_of(record.text)
        if record.attributes.get('schedule') == 1:
            number = record.attributes['principle']
            record.attributes['legal_context'] = [
                {'uid': 'wa-pris:s 14', 'label': 'Entities in scope'},
                {'uid': 'wa-pris:s 223', 'label': 'Application to existing information'},
            ]
            if number in (1, 7, 8, 10):
                record.attributes['scope_note'] = 'Applies to information collected on or after 1 July 2026 (s 223).'
            if number == 6:
                record.attributes['legal_context'].append({'uid': 'wa-pris:s 27', 'label': 'IPP 6 exclusions and FOI access route'})
        if record.attributes.get('section') == 79:
            record.attributes['legal_context'] = [{'uid': 'wa-pris:s 227', 'label': 'Existing activities and significant changes'}]
        if record.attributes.get('section') in (151, 170, 225):
            record.attributes['scope_note'] = 'This section refers to breach provisions that are not yet in force in the July 2026 consolidation.'
        corpus.add_control(record)
    return {'sections': len(section_numbers), 'privacy_principles': 11,
            'sharing_principles': 5, 'records': len(records),
            'provisions': sum(bool(c.text) for c in records)}
