# Scripts

These scripts prepare data, generate examples and review sources or assessment
commands. Run them from the repository root. Scripts that use publisher documents
need the relevant [sources acquired first](../sources/README.md).

## Generate examples

| Script | What it does and where it writes |
|---|---|
| `build_telemetry_examples.py` | Creates fictional security events and a scope manifest for each year under `examples/telemetry/2023/`, `2024/` and `2025/`. |
| `prepare_assessment_examples.py` | Checks policy identifiers and prepares assessment prompts and fictional ratings in `data/department-assessment-policy.json` and `data/department-assessment-examples.json`. |
| `build_assessment_examples.mjs` | Builds a blank assessment spreadsheet and three completed examples in `examples/assessments/` and `../outputs/department-assessments-20260916/`; saves previews under `data/review/assessment-build/`. |

For example:

```powershell
python tools/build_telemetry_examples.py
```

This overwrites the generated log examples and does not connect to a tenant. See the
[log example guide](../examples/telemetry/README.md) for outputs and usage.

Workbook generation uses Node.js and the `@oai/artifact-tool` authoring dependency.
See [rebuilding the workbook examples](../docs/department-assessments.md#rebuilding-the-workbook-examples)
for setup. This dependency is not needed to run the application.

## Review sources and coverage

| Script | Purpose and output |
|---|---|
| `revalidate_corpus.py` | Checks corpus records, workspace mappings and coverage; updates `data/validation/corpus-revalidation.json` and `docs/corpus-revalidation.md`. |
| `analyse_topics.py` | Counts topic coverage in the corpus and writes `data/validation/topic_prevalence.json`. |
| `framework_gap_report.py` | Reviews the mapping inventory for missing frameworks and writes `data/framework-review.json` and `docs/framework-coverage-review.md`. |
| `validate_framework.py` | Previews an OSCAL file and checks its records before import; prints results without registering the framework. |
| `verify_against_source.py` | Compares extracted records with publisher sources and prints verification results. |
| `review_asd_principles.py` | Compares the acquired principles page with loaded records and writes `data/validation/asd-principles-review.json`. |
| `review_wa_pris.py` | Retrieves the official Act text, compares it with the extract and writes `data/validation/wa-pris-review.json`. |

Use `python -m wacc sources` for normal downloads. See the
[acquisition guide](../sources/README.md) for options, or the
[framework import guide](../sources/add-framework.md) to add a new source and its
controls, mappings and assessments.

## Prepare extracts

The `extract_*.py` scripts handle particular publisher formats. `curate_800_88.py`
prepares a reviewed guidance extract, and `textjoin.py` joins wrapped text used by
the extractors. Inputs, dependencies and output locations vary by script; check
its opening instructions before running it. Reviewed extracts belong in
`data/corpus/`; intermediate review files generally stay in ignored `data/review/`.

## Review assessment commands

| Script | Purpose |
|---|---|
| `review_assessment_sources.py` | Downloads referenced command documentation into `data/review/assessment-sources/` and records retrieval results in that folder's `retrieval.json`. |
| `validate_assessment_commands.ps1` | Parses the assessment commands and reports syntax, command names and parameters. It does not execute the assessment commands. |
| `check_assessment_doc_parameters.py` | Compares parsed command parameters with the cached official documentation. |

Follow the [assessment authoring steps](../sources/add-framework.md#5-add-or-revise-the-assessments)
for the command sequence and required review. See [tests](../tests/README.md) for
regression checks and offline command fixtures.
