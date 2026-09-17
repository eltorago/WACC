"""Compare imported provisions with the publisher's independent HTML rendition."""
from datetime import date
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc.loaders import wa_pris
from wacc.model import Corpus
from wacc.registry import FRAMEWORKS_BY_KEY
from wacc.sources import _read, local_path, source_directory

HTML_URL = 'https://www.legislation.wa.gov.au/legislation/statutes.nsf/RedirectURL?OpenAgent=&query=mrdoc_49691.htm'


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def normalise(text):
    # Word encodes non-breaking hyphens separately; HTML uses Unicode. Compare
    # every letter and number in order, ignoring layout and punctuation encoding.
    return ''.join(c for c in text.casefold() if c.isalnum())


def compare(corpus, page):
    parser = Text()
    parser.feed(page.decode('utf-8-sig'))
    text = normalise(''.join(parser.parts))
    records = corpus.controls_for('wa-pris')
    failed = [c.uid for c in records if c.text and normalise(c.text) not in text]
    if failed:
        raise ValueError('Imported wording differs from publisher HTML: ' + ', '.join(failed))
    return sum(bool(c.text) for c in records)


def main():
    corpus = Corpus()
    framework = FRAMEWORKS_BY_KEY['wa-pris']
    corpus.add_framework(framework)
    counts = wa_pris.load_into(corpus, framework, local_path(source_directory(), wa_pris.SOURCE_FILE))
    page, _, _ = _read(HTML_URL)
    checked = compare(corpus, page)
    mappings = json.loads((ROOT/'data/workspace-frameworks.json').read_text(encoding='utf-8'))
    refs = [(key, m) for key, values in mappings.items() for m in values if m['uid'].startswith('wa-pris:')]
    result = {'reviewed_on': date.today().isoformat(), 'edition': wa_pris.EDITION,
              'source_url': wa_pris.SOURCE_URL, 'source_sha256': wa_pris.REVIEWED_SHA256,
              'comparison_url': HTML_URL, 'comparison_sha256': hashlib.sha256(page).hexdigest(),
              'comparison': 'Every imported provision matches the HTML rendition after removing punctuation and whitespace.',
              'provisions_compared': checked, 'counts': counts,
              'workspace_mappings': len(refs), 'workspace_controls': len({key for key, _ in refs}),
              'text_sha256': {c.uid: hashlib.sha256(c.text.encode()).hexdigest() for c in corpus.controls_for('wa-pris') if c.text}}
    (ROOT/'data/validation/wa-pris-review.json').write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print('WA PRIS: %d provisions match the publisher HTML; %d workspace mappings.' % (checked, len(refs)))


if __name__ == '__main__': main()
