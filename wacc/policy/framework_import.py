"""Parse publisher data in the bounded worker. Never import executable rules."""
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path

from .contracts import PolicyError
from .documents import MAX_BYTES, checked_archive, local_file


def parse(framework, path):
    path = local_file(path)
    if path.stat().st_size > MAX_BYTES:
        raise PolicyError('Framework file exceeds the 16 MiB limit.')
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if framework == 'wa-csp':
        from .wa_parser import parse as parse_wa
        value = parse_wa(path)
        metadata = dict(id=framework, title=value['title'], edition=value['title'])
        rows = [dict(id='wa-csp:' + r['identifier'], frameworkId=framework, officialReference=r['identifier'],
                     heading=r['section_title'], parentId=r['section_number'], authoritativeText=r['text'],
                     context=r.get('lead_in',''), sourceLocator=dict(reference=r['identifier'],section=r['section_number']))
                for r in value['records']]
        mappings = []
    elif framework in ('ism', 'aescsf'):
        from ..model import Corpus
        from ..registry import FRAMEWORKS_BY_KEY
        from ..loaders import oscal, aescsf
        from ..io.xlsx import Workbook
        from ..model import normalise_identifier
        existing = Corpus()
        fw = deepcopy(FRAMEWORKS_BY_KEY[framework])
        existing.add_framework(fw)
        mappings = []
        if framework == 'ism':
            value = json.loads(raw)
            title = value.get('catalog', {}).get('metadata', {}).get('title', '')
            if 'information security manual' not in title.casefold():
                raise PolicyError('The download is not an ISM catalogue.')
            oscal.load_into(existing, fw, str(path), applicability_prop='applicability')
        else:
            with checked_archive(raw) as archive:
                if any('vbaproject' in n.lower() for n in archive.namelist()):
                    raise PolicyError('Macro-enabled framework workbooks are not supported.')
                for name in archive.namelist():
                    if name.endswith(('.xml','.rels')):
                        xml = archive.read(name).upper()
                        if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
                            raise PolicyError('External entity declarations are not supported.')
            aescsf.load_into(existing, fw, str(path))
            book = Workbook(str(path))
            headings, body = book.table()
            indexes = {name:i for i,name in enumerate(headings)}
            for values in body:
                practice = values[indexes['Practice ID']].strip()
                for ism, _ in aescsf.parse_australian_references(values[indexes['Australian References']]):
                    mappings.append(dict(source='aescsf:' + normalise_identifier(practice), target='ism:' + normalise_identifier(ism),
                                         relationship='RelatedTo', relation='MappedOnly', provenance='AEMO Australian References column',
                                         reviewStatus='Publisher mapping; target edition may differ'))
        metadata = dict(id=framework,title=fw.name,edition=fw.revision or '')
        controls = [c for c in existing.controls_for(framework) if c.text and not c.attributes.get('structural')
                    and (framework != 'aescsf' or c.depth == 2)
                    and (framework != 'ism' or re.fullmatch(r'ISM-\d+',c.identifier,re.IGNORECASE))]
        rows = []
        for c in controls:
            parent = existing.controls.get(c.parent_uid)
            rows.append(dict(id=c.uid,frameworkId=framework,officialReference=c.identifier,heading=c.title or c.section_ref or '',
                             parentId=c.parent_uid,authoritativeText=c.text,
                             context=parent.text if framework == 'aescsf' and parent else c.attributes.get('lead_in',''),
                             sourceLocator=dict(reference=c.identifier)))
    else:
        raise PolicyError('Unsupported framework import.')
    if not metadata['edition'] or not 1 <= len(rows) <= 20000 or len({r['id'] for r in rows}) != len(rows):
        raise PolicyError('Framework has no edition, invalid counts or duplicate requirements.')
    if sum(len(r['authoritativeText']) + len(r['context']) for r in rows) > 8_000_000:
        raise PolicyError('Framework text exceeds supported limits.')
    metadata.update(sourceHash=digest, sourceFile=path.name, licence='Publisher source imported locally; redistribution permission is not granted by this import.')
    return dict(framework=metadata, requirements=rows, mappings=mappings)
