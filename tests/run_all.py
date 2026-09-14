"""Every suite, in layers, lowest first.

Order is not cosmetic. A vocabulary defect breaks search, search breaks the analysis
payload, and the payload breaks every renderer, so a run that reports twelve failures
across five suites is usually one defect and eleven consequences. Running lowest first and
naming the layer makes the first failure the one worth reading.

--injected adds the matrix at the end: every recorded defect is put back, one at a
time, and the suite that was written for it has to fail. It is opt-in because it runs
these suites tens of times over.

A suite may exit non-zero and still be a clean run. Three of these record plan corrections
— cases where a criterion fixed before the code turned out to be the wrong question, kept
as written with a corrected measure beside it — and those count as failures by design. The
summary separates them from real failures, and the exit code follows the real ones.
"""

import os
import subprocess
import sys
import time
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Lowest layer first. Each names what breaks everything above it if it fails.
LAYERS: List[Tuple[str, str, List[str]]] = [
    ("vocabulary", "spelling, stemming, aliases and concepts", ["test_terms.py"]),
    ("corpus", "what loaded, under what licence, and quoting which table",
     ["test_source_permissions.py", "test_patch_integration.py", "test_packaging.py", "test_extracts.py"]),
    ("retrieval", "exact identifiers, then topical search",
     ["test_identifier_lookup.py", "test_topical_search.py"]),
    ("structure", "hierarchy, links, the threat layer and the maturity model",
     ["test_relate.py", "test_threat.py", "test_ztmm.py", "test_c2m2.py"]),
    ("meaning", "thresholds, the analysis payload, archetypes and derivation",
     ["test_analysis.py", "test_derive.py", "test_uplift.py"]),
    ("presentation", "layout arithmetic, the three renderers and the server",
     ["test_render.py", "test_navigation.py"]),
]


def _run(name: str) -> Tuple[int, str, float]:
    started = time.time()
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, name)],
        capture_output=True, text=True, cwd=ROOT,
    )
    return result.returncode, result.stdout + result.stderr, time.time() - started


def _counts(output: str) -> Tuple[int, int, int]:
    """Passes, failures and plan corrections, read from the suite's own last line."""
    passes = output.count("  pass ")
    corrections = output.count("PLAN WRONG")
    failures = output.count("  FAIL ")
    return passes, failures, corrections


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = "-v" in argv or "--verbose" in argv
    injected = "--injected" in argv

    total_pass = total_fail = total_corrected = 0
    broken: List[str] = []
    print("wacc regression suite — %d layers\n" % len(LAYERS))

    for layer, what, suites in LAYERS:
        print("== %-14s %s" % (layer, what))
        for suite in suites:
            code, output, elapsed = _run(suite)
            passes, failures, corrections = _counts(output)
            real = failures - corrections if failures >= corrections else failures
            total_pass += passes
            total_fail += real
            total_corrected += corrections
            status = "ok" if code == 0 else "FAILED"
            note = ""
            if corrections:
                note = "  (%d plan correction%s)" % (
                    corrections, "" if corrections == 1 else "s"
                )
            print(
                "   %-26s %-7s %4d passed  %3d failed%s  %5.1fs"
                % (suite, status, passes, real, note, elapsed)
            )
            if code != 0:
                broken.append(suite)
            if verbose or code != 0:
                for line in output.splitlines():
                    if line.startswith("  FAIL") or line.startswith("        from:"):
                        print("      %s" % line.strip())
        print()

    print("-" * 72)
    print(
        "%d passed, %d failed, %d recorded as plan corrections"
        % (total_pass, total_fail, total_corrected)
    )
    if broken:
        print("suites exiting non-zero: %s" % ", ".join(broken))
        print("Read the lowest layer first: the ones above it usually follow from it.")
    else:
        print("Every layer clean.")

    # A clean run says nothing about whether anything is being watched. The matrix puts
    # each recorded defect back and checks that a named case fails. It runs the suites
    # tens of times over, so it is opt-in — but it is named either way, because a matrix
    # nobody runs is worse than no matrix.
    matrix = 0
    if injected:
        print()
        result = subprocess.run(
            [sys.executable, os.path.join(HERE, "injected.py")],
            text=True, cwd=ROOT,
        )
        matrix = result.returncode
    else:
        print("\nInjected-regression matrix not run. tests/run_all.py --injected puts "
              "each\nrecorded defect back and checks that a named case fails "
              "(about four minutes).")
    return 1 if (broken or matrix) else 0


if __name__ == "__main__":
    sys.exit(main())
