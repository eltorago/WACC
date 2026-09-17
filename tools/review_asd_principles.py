"""Compare the linked ASD principles page with the official ISM OSCAL catalogue."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc.loaders.oscal import load_catalog, walk_controls, preferred_label, statement_text
from wacc.loaders.principles import IDENTIFIERS, FUNCTIONS
from wacc.sources import source_directory, local_path


class PrinciplesPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.item = None
        self.records = []

    def handle_starttag(self, tag, attrs):
        if tag == 'li': self.item = []

    def handle_data(self, text):
        if self.item is not None: self.item.append(text)

    def handle_endtag(self, tag):
        if tag == 'li' and self.item is not None:
            text = ' '.join(''.join(self.item).split())
            match = re.fullmatch(r'((?:GOV|IDE|PRO|DET|RES|REC)-\d{2}) – ([^:]+): (.+)', text)
            if match: self.records.append(match.groups())
            self.item = None


def compare(page, catalog):
    parser = PrinciplesPage()
    parser.feed(page.decode('utf-8'))
    expected = [(preferred_label(c), c['title'], statement_text(c, {}))
                for c, _, _, _ in walk_controls(catalog) if c.get('class') == 'ISM-principle']
    if len(parser.records) != 49 or {r[0] for r in parser.records} != set(IDENTIFIERS):
        raise ValueError('Publisher page must contain exactly the reviewed 49 principle identifiers.')
    if parser.records != expected:
        raise ValueError('Principle order, identifiers, titles or full statements differ between the page and OSCAL.')
    return parser.records


def main():
    cache = source_directory()
    page_path = local_path(cache, 'asd-cyber-security-principles-2026-09.html')
    catalog_path = local_path(cache, 'ISM_catalog.json')
    records = compare(page_path.read_bytes(), load_catalog(str(catalog_path)))
    report = {
        'reviewed_on': '2026-09-17', 'edition': 'September 2026',
        'page_url': 'https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/ism/cyber-security-principles',
        'catalog_version': load_catalog(str(catalog_path))['metadata']['version'],
        'page_sha256': hashlib.sha256(page_path.read_bytes()).hexdigest(),
        'catalog_sha256': hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        'principles': len(records),
        'functions': {name: len(numbers) for name, (_, numbers) in FUNCTIONS.items()},
        'comparison': 'All identifiers, titles, complete statements and publisher order match exactly after HTML whitespace normalisation.',
        'principle_text_sha256': {id_: hashlib.sha256(text.encode()).hexdigest() for id_, _, text in records},
    }
    output = ROOT / 'data/validation/asd-principles-review.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(records)} principle statements match the ASD page and ISM OSCAL catalogue.')


if __name__ == '__main__': main()
