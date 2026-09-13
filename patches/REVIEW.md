# Claude patch integration review — 14 September 2026

All four delivered patches were reviewed and integrated in application order:

1. GUI cards, visible risks, control detail panels, and working-paper exports.
2. Source-text extraction and corpus corrections, with source comparison tooling.
3. Essential Eight strategy matching corrections and regression cases.
4. Content-based patch tracking, merged with the existing source-permission rules.

## Corrections made during integration

- Preserve suspended hyphens when joining wrapped source lines (for example,
  `security- and privacy-related`), including newline-separated conjunctions.
- Resolve original patch commits to actual integration commits. Refuse to replace
  audit evidence when a commit is unavailable or the manifest has no file evidence.
- Keep the reviewed source allowlist and hash validation when merging packaging
  exclusions. Existing delivered patches remain tracked as historical evidence.
- Make cards the server default and verify that explicit grid/card URLs still work.

## Validation

The full suite before the remaining patches reported 403 passed and five failures.
The final suite reports 415 passed and the same five failures, plus 19 recorded plan
corrections. The runner separately executes seven source-permission unittest cases
and three integration unittest cases; all ten pass but are not included in its pass
counter. Packaging reports zero violations. All 90 rendering checks pass.

The unchanged failures are three packaging tests (missing `data/raw` fixtures, an
empty excluded-directory fixture, and inherited `WACC_SOURCES` affecting the staged
absence test), one guidance-document presence test, and one benchmark-detail test
because extracted detail files are absent. These are not a clean full-suite result.

Commands: `python tests/run_all.py`, `python tests/test_patch_integration.py`,
`python tests/test_source_permissions.py`, and `python -m wacc.packaging --check`.
Tests used UTF-8 mode and `WACC_SOURCES` pointing at the parent source directory.
The injected-regression matrix and full PDF source-comparison run were not run.

## Remaining GUI limitations

The delivered card view still groups by framework. Framework toggles hide columns
in the browser; they do not scope retrieval or exports. Published assessment detail
depends on available source/detail data; derived procedures are labelled separately.
This integration does not complete the requested control-centric redesign.

See `APPLIED.json` for integration commits and `MANIFEST.json` for content evidence.
