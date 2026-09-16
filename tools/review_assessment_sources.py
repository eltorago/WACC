"""Refresh the local, ignored research cache for official assessment documentation.

Downloads documentation only; never imports or executes downloaded code.
"""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data/review/assessment-sources'


class MainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.text = []; self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.skip += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)
        if tag in ('p', 'li', 'h1', 'h2', 'h3', 'tr', 'pre'): self.text.append('\n')

    def handle_data(self, text):
        if not self.skip: self.text.append(text)


def fetch(item):
    key, source = item
    try:
        request = urllib.request.Request(source['url'], headers={'User-Agent': 'WACC documentation review/1.0'})
        with urllib.request.urlopen(request, timeout=35) as response:
            body = response.read(8 * 1024 * 1024)
            final_url = response.url
        parser = MainText(); parser.feed(body.decode('utf-8'))
        text = ''.join(parser.text)
        (CACHE / (key + '.txt')).write_text(text, encoding='utf-8')
        missing = [term for term in source.get('verify_terms', []) if term.casefold() not in text.casefold()]
        return key, dict(url=source['url'], final_url=final_url, sha256=hashlib.sha256(body).hexdigest(),
                         reviewed_on='2026-09-16', status='needs-review' if missing else 'retrieved', missing_terms=missing)
    except Exception as error:
        return key, dict(url=source['url'], status='unavailable', error=str(error))


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    sources = json.loads((ROOT / 'data/assessment-sources.json').read_text(encoding='utf-8'))
    if len(sys.argv) > 1: sources = {key: sources[key] for key in sys.argv[1:]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(fetch, sources.items()))
    report = CACHE / 'retrieval.json'
    old = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
    old.update(results); report.write_text(json.dumps(old, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in results.items() if v['status'] != 'retrieved'}, indent=2))
    print('Retrieved', sum(v['status'] == 'retrieved' for v in results.values()), 'of', len(results))


if __name__ == '__main__': main()
