"""Measure local policy workflows; compare output hashes before and after changes.

Run with a saved assessment containing synthetic documents. No downloads occur.
Timings describe this machine and corpus, not a performance guarantee.
"""
import argparse
import gc
import json
from pathlib import Path
import platform
import statistics
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wacc.policy import alignment, corpus, reports, service, store
from wacc.policy.contracts import fingerprint


def measure(operation, repeat):
    elapsed = []
    for _ in range(repeat):
        gc.collect()
        start = perf_counter()
        result = operation()
        elapsed.append((perf_counter() - start) * 1000)
    return dict(medianMs=round(statistics.median(elapsed), 3),
                samplesMs=[round(value, 3) for value in elapsed], outputHash=fingerprint(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assessment', type=Path)
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 20:
        parser.error('--repeat must be between 1 and 20')
    state = store.load(args.assessment)
    run, events = state['run'], state['events']
    operations = {
        'selectedCorpus': lambda: corpus.load('wa-csp', corpus_version=corpus.CORPUS_VERSION, also=('ism', 'aescsf')),
        'frameworkInventory': corpus.installed,
        'openAssessment': lambda: store.load(args.assessment),
        'frameworkCoverage': lambda: service.framework_summaries(run, events),
        'alignmentComparison': lambda: alignment.compare(run['requirements'], run['documents']),
        'htmlReport': lambda: reports.render(state, 'html'),
        'jsonReport': lambda: reports.render(state, 'json'),
    }
    results = dict(python=platform.python_version(), platform=platform.platform(),
                   requirements=len(run['requirements']), frameworks=len(run['versions']['frameworks']),
                   measurements={name: measure(operation, args.repeat) for name, operation in operations.items()})
    args.output.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
