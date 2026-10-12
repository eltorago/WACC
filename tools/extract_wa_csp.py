"""Extract the reviewed 2026 WA policy from the local source cache."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from wacc.sources import source_directory, local_path
from wacc.wa_policy import parse, write_cache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=local_path(source_directory(), 'wa-cyber-security-policy.pdf'))
    parser.add_argument('--output', type=Path, default=HERE / 'data/corpus/wa-csp.json')
    args = parser.parse_args()
    data = parse(args.source)
    write_cache(args.output, data)
    print('%s: %d headings, %d clause records across %d pages' %
          (data['title'], len(data['contents_sections']), len(data['records']), data['page_count']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
