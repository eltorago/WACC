"""Run the WACC checks in dependency order and report one combined result.

Lower-level checks run first so a source or search problem appears before the presentation
failures it may cause. ``--injected`` additionally restores known defects one at a time and
confirms that the appropriate regression check detects them.
"""

import os
import re
import subprocess
import sys
import time
from typing import List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Lowest layer first. Each names what breaks everything above it if it fails.
LAYERS: List[Tuple[str, str, List[str]]] = [
    ("vocabulary", "spelling, stemming, aliases and concepts", ["test_terms.py"]),
    ("corpus", "what loaded, under what licence, and how source text is cleaned",
     ["test_source_permissions.py", "test_source_workflow.py", "test_framework_import.py", "test_textjoin.py", "test_packaging.py", "test_extracts.py"]),
    ("retrieval", "exact identifiers, then topical search",
     ["test_identifier_lookup.py", "test_topical_search.py"]),
    ("structure", "hierarchy, links, the threat layer and the maturity model",
     ["test_relate.py", "test_threat.py", "test_ztmm.py", "test_c2m2.py", "test_framework_families.py"]),
    ("meaning", "thresholds, the analysis payload, archetypes and derivation",
     ["test_analysis.py", "test_derive.py", "test_assessment.py", "test_corpus_assessment.py", "test_assessment_procedures.py"]),
    ("presentation", "layout arithmetic, the three renderers and the server",
     ["test_render.py", "test_navigation.py", "test_control_workspace.py", "test_extended.py"]),
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
    unit=re.search(r'Ran (\d+) tests? in ',output)
    if unit:
        failure=re.search(r'FAILED \(([^)]+)\)',output)
        failures=sum(int(n) for n in re.findall(r'(?:failures|errors)=(\d+)',failure[1])) if failure else 0
        skipped=re.search(r'skipped=(\d+)',output)
        passes=int(unit[1])-failures-(int(skipped[1]) if skipped else 0)
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
                    if line.startswith(("  FAIL","        from:","FAIL:","ERROR:","  File ","AssertionError:","ValueError:","ImportError:")):
                        line=line[:700]
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
