"""Extract the reviewed 2026 WA policy, including its nested technical clauses."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

TITLE = 'Western Australian Government Cyber Security Policy 2026'
SOURCE_SHA256 = '4be54cb6ead0f614ff72f90b65690e5b3ad7fcf891c1c31627922a9d286d1ac9'
HEADING = re.compile(r'^([1-6](?:\.\d+){0,2})\.?\s+(.+)$')
LETTER = re.compile(r'^([a-z])\.\s+(.+)$')


def clean_wrapping(text):
    text = re.sub(r'(?<=\w)-\s+(?!(?:and|or)\b)(?=[a-z])', '-', text)
    return re.sub(r'(https?://[^\s]+[./-])\s+(?=\w)', r'\1', text)


def ensure_current(cache, source):
    """Refresh missing/old extracts from the reviewed local PDF, never reuse 2024 IDs."""
    cache = Path(cache)
    if cache.exists():
        try:
            data = json.loads(cache.read_text(encoding='utf-8'))
            if data.get('edition') == '2026' and data.get('source_sha256') == SOURCE_SHA256:
                return
        except (ValueError, AttributeError):
            pass
    source = Path(source)
    if not source.exists():
        raise ValueError('Download the 2026 WA CSP on the Sources page, then reload the corpus.')
    try:
        data = parse(source)
    except ImportError as exc:
        raise ValueError('Install pdfplumber (python -m pip install pdfplumber) to import the 2026 WA CSP.') from exc
    write_cache(cache, data)


def write_cache(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name, suffix='.tmp', delete=False) as f:
            stage = Path(f.name)
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write('\n')
        os.replace(stage, path)
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def records_for(section):
    """Keep indented Roman lists with their lettered requirement and its context."""
    records, context, pending = [], [], []
    letter_indent = None
    for line, x, page in section['body']:
        match = LETTER.match(line)
        if match and (letter_indent is None or abs(x - letter_indent) < 2):
            expected = chr(ord('a') + len(records))
            if match[1] != expected:
                raise ValueError('Unexpected clause sequence in ' + section['number'])
            letter_indent = x
            if pending:
                context = pending
                pending = []
            records.append(dict(identifier=section['number'] + match[1],
                section_number=section['number'], section_title=section['title'],
                lead_in=' '.join(context), text=match[2], page=page))
        elif records and x > letter_indent + 2 and not pending:
            records[-1]['text'] += ' ' + line
        elif records:
            pending.append(line)
        else:
            context.append(line)
    if not records and context:
        records.append(dict(identifier=section['number'], section_number=section['number'],
            section_title=section['title'], lead_in='', text=' '.join(context), page=section['page']))
    if pending:
        # Prose after a list belongs to the section, not to its last lettered item.
        section['notes'] = ' '.join(pending)
    return records


def parse(path):
    path = Path(path)
    source_bytes = path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError('WA CSP source differs from the reviewed 2026 edition; review the new file before importing it.')
    import pdfplumber
    sections, current, started = [], None, False
    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            # Footnotes, page furniture and superscript note markers use smaller fonts.
            words = page.filter(lambda obj: obj.get('object_type') != 'char' or obj['size'] >= 11).extract_words(extra_attrs=['size'])
            lines = []
            for word in words:
                if not lines or abs(word['top'] - lines[-1][0]) > 3:
                    lines.append((word['top'], [word]))
                else:
                    lines[-1][1].append(word)
            for _, row in lines:
                text = ' '.join(w['text'] for w in row)
                heading = HEADING.match(text) if row[0]['size'] >= 13 else None
                if not started:
                    if heading and heading[1] == '1' and heading[2] == 'Govern' and row[0]['size'] >= 24:
                        started = True
                    else:
                        continue
                if text == 'Annual Implementation Reporting' and row[0]['size'] >= 13:
                    break
                if heading:
                    current = dict(number=heading[1], title=heading[2], page=page_no, body=[])
                    sections.append(current)
                elif current is not None and row[0]['size'] >= 13 and not current['body'] and current['number'].count('.'):
                    current['title'] += ' ' + text
                elif current is not None:
                    current['body'].append((text, row[0]['x0'], page_no))
            else:
                continue
            break
        page_count = len(pdf.pages)
    functions = {s['number']: s['title'] for s in sections if '.' not in s['number']}
    numbers = [s['number'] for s in sections]
    if len(numbers) != len(set(numbers)) or len(functions) != 6 or '3.14.3' not in numbers or numbers[-1] != '6.2':
        raise ValueError('Could not extract the complete 2026 policy structure: ' + ', '.join(numbers))
    records = [record for section in sections for record in records_for(section)
               if '.' in section['number'] or 'must' in record['text'].lower()]
    for record in records:
        for key in ('text', 'lead_in'):
            record[key] = clean_wrapping(record[key])
    if page_count != 44 or len(sections) != 58 or len(records) != 218:
        raise ValueError('The 2026 WA CSP extraction is incomplete; expected 44 pages, 58 headings and 218 clause records.')
    return dict(source_file=path.name, title=TITLE, edition='2026', source_sha256=SOURCE_SHA256,
        page_count=page_count, contents_sections={s['number']: s['title'] for s in sections},
        functions=functions, records=records,
        section_notes={s['number']: s['notes'] for s in sections if s.get('notes')})
