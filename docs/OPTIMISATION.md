# Code optimisation and alignment workflow

23 September 2026. Measured against `41b6f02`, the first native policy pilot.

## Changes made

| Priority | Area | Improvement |
|---|---|---|
| High | Corpus loading | Load only selected frameworks and their source dependencies. Keep one loading pipeline for the desktop and existing library. |
| High | Alignment workflow | Index policy sentences once, then search every selected requirement. Save results so opening and selecting requirements does not rerun the comparison. |
| High | Imports | Accept multiple files and ZIPs through the same bounded parser. Keep member names and source hashes, deduplicate content and report unreadable files. |
| Medium | Reports and summaries | Render file exports once. Aggregate existing rows without repeatedly copying the entire assessment for each framework. |
| Medium | Shared state | Copy framework metadata per load; source revisions no longer mutate the global registry. Review views cannot change saved event objects. |
| Medium | Duplicate code | Share the WA parser with the extraction script. Generate only schema definitions used by each standalone contract. |
| Low | Dependencies and documentation | Separate runtime dependencies from build/test tools; replace the old review instructions with the alignment workflow. |

The desktop now shows **Mentioned**, **Related wording**, **Not mentioned** and
**Unable to check**, with source passages. Reviewer approval and finalisation
steps were removed from this interface. Historical assessment data and the
existing control-library web app are preserved. Legacy review commands remain
for compatibility; they do not drive the alignment view.

## Measurements

Median of three local runs, Python 3.13.15 on Windows 10, using an existing saved
assessment with 1,583 requirements across three frameworks. No network requests
were made. These are development-machine measurements, not deployment guarantees.

| Operation | Before | After |
|---|---:|---:|
| Load the three selected frameworks | 2,180 ms | 66 ms |
| List available assessment frameworks | 2,157 ms | 106 ms |
| Legacy per-framework review aggregation | 50 ms | 19 ms |
| Open and validate the saved assessment | 22 ms | 25 ms |

The four operations above returned identical result hashes before and after.
The new alignment search took 77 ms on that small policy-text fixture. Its report
content differs intentionally from the old review report, so report timings are
not treated as an equivalent before/after comparison.

Reproduce measurements with a saved comparison containing synthetic documents:

```powershell
python tools/benchmark_policy.py comparison.wacc --repeat 3 --output timings.json
```

The local measurements are in `data/local/optimisation-before.json` and
`data/local/optimisation-final.json`. The script reports every sample and output
hash. New comparisons store alignment results; older files compute alignment
from their retained text when opened or exported.

## Validation

- Full regression suite: **603 passed, 0 failed**, plus 19 existing test-plan corrections.
- After the final excerpt-size change: **25 alignment, 41 saved-policy and 8
  framework-update checks passed**. The alignment suite uses synthetic policy text.
- Selective loading produces the same selected controls and published links as
  loading the whole library; unrelated frameworks and threat data stay unloaded.
- The shared WA PDF parser reproduces all 86 existing source records after
  whitespace normalisation.
- ZIP tests cover traversal, Windows filename normalisation, links, expansion
  limits, member counts, unreadable members, duplicates and source verification.
- Saved results validate each matching passage and span against the recorded
  source. Report filters and summary exports preserve the original data.
- Match excerpts contain only their source window (up to 1,600 characters),
  preventing long PDF paragraphs from being copied into every matched requirement.
- Native widget tests cover requirement selection and status filtering.
- Packaging check: **0 violations**. Publisher files and generated examples/builds
  remain outside Git.

`data/local/optimisation-alignment-tests-final.txt` contains the full-suite output.
The synthetic two-file ZIP demonstration is under `data/local/alignment-example/`.

## Remaining work

| Priority | Next step | Why it matters |
|---|---|---|
| High | Benchmark retrieval against independently labelled real policy collections. | Lexical matches can miss paraphrases or identify related topics without semantic agreement. The UI shows passages and uncertainty rather than compliance scores. |
| Medium | Confirm whether existing integrations still need the legacy review commands. | Retiring them later would simplify the service and saved-data contracts, but needs a defined compatibility window. |
| Medium | Finish managed-endpoint, signing, accessibility and clean-machine acceptance. | Automated desktop tests and an unsigned local build do not establish enterprise deployment readiness. |

The current matching rules and file limits are described in the
[technical reference](policy-review.md).
