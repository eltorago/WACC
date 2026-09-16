# Department assessment design and validation

The Assessments page imports the WACC XLSX template for the WA Cyber Security Policy
2024. It retains the department, reporting year, assessment date, assessor, scope,
approval and AIR details, requirement ratings, evidence, actions and owners.

The template covers all **86 requirement records** in the existing WA policy extract.
`data/department-assessment-policy.json` contains WACC's assessment prompts and their
policy identifiers. No heading-only corpus records are scored. Reporting and exemption
fields follow page 22 of the policy and are kept outside the numerical ratings.
Source links use the locally acquired policy in the corpus; workspace links use the
existing reviewed control mappings.

The fictional examples have average ratings of **1.00**, **2.44** and **3.70** for 2023,
2024 and 2025. Every policy area improves. The 2023 example is retrospective. Evidence
references, observations, department roles and reporting records are all fictional.

## Calculation

WACC's progress scale is 0 Not started, 1 Planned, 2 Partly implemented, 3 Implemented
and 4 Tested and reviewed. The policy does not prescribe this aggregate scale.

Each applicable requirement contributes equally to the mean. A score is unavailable
until every applicable requirement has a rating. N/A requires a reason and is excluded;
Not assessed is outstanding work. The trend compares the intersection of applicable
requirements across the department's years. Each area/year cell uses that year's scope
and displays the number rated and excluded. Different declared scopes are called out.

The server calculates results from input ratings. It ignores workbook formula caches.
The workbooks calculate their own summaries for use in Excel; those summaries agree
with the server for each example.

## Import and storage

The server accepts up to ten XLSX files, 5 MB per file and 20 MB per batch. The bounded
ZIP/XML reader does not extract files, execute formulas or resolve workbook links.
It rejects macros, external workbook links, XML entities, duplicate workbook parts,
oversized contents, missing or duplicate requirements, altered criteria and invalid
ratings. Assessment input cells must contain values rather than formulas.

All files in a batch are validated before writing. One record is stored per normalised
department name and year. Importing identical bytes is idempotent. Replacing a changed
workbook requires the explicit replacement checkbox. Writes use a temporary file and
atomic replacement; threads share a lock. Run one server against a given storage folder.

`data/local/assessments/records.json` holds the parsed records, original filenames,
SHA-256 hashes and import timestamps. Original uploads are not retained. Keep the XLSX
files and back up the JSON file. `WACC_ASSESSMENTS` can point to a different storage
folder. Only the four named authored workbooks are allowed into Git/release packages;
department imports and publisher source workbooks remain excluded.

## Validation performed

- 21 assessment tests cover the real XLSX files, policy coverage, formula caches,
  missing/N/A/zero ratings, reporting fields, department identity, persistence,
  replacement, batch atomicity, malformed uploads and escaped display text.
- HTTP tests cover multipart imports, downloads, example imports and request tokens.
- The complete repository regression suite passed: 515 checks, zero failures, with
  19 existing plan corrections recorded separately.
- Browser verification covered the empty state, all three example imports, file-picker
  uploads, duplicate protection, replacement, year navigation and policy-area filtering.
- Every worksheet was rendered and inspected. Formula edits were exercised for a missing
  rating and an exclusion, restored, recalculated and exported. Dropdowns, filter tables,
  frozen headings/identifier columns and Excel date values were checked in the XLSX.
- Excel desktop recalculation was not exercised. Formula evaluation and previews used
  the bundled spreadsheet runtime; the application has no new runtime dependencies.

## Validate annual assessments with logs

Annual assessments can now be checked against imported Sentinel and Defender event
exports. Open **Validate against security logs** to compare fourteen telemetry checks,
inspect event references and save reviewer decisions. The annual page keeps the
reported maturity trend and shows evidence findings separately for each year.
See [the collection and validation guide](telemetry-validation.md) for the fictional
log examples, ADLS Gen2 connection and Sentinel data-lake CSV workflow.

## Rebuilding the workbook examples

`tools/prepare_assessment_examples.py` checks identifiers against the locally acquired
WA policy extract and writes the authored prompts and fictional data. Change the prompt
source and example observations there, then run it from the repository root.

`tools/build_assessment_examples.mjs` uses the bundled `@oai/artifact-tool` spreadsheet
runtime. It resolves that dependency through a temporary `node_modules` junction in
`data/review/assessment-build/`, writes previews in that ignored folder and exports the
four workbooks into `examples/assessments/` and the workspace output directory. Remove
the junction after building. This authoring dependency is not needed to run WACC.

After changes, run `python -m unittest tests.test_department_assessments` and
`python tests/run_all.py` with UTF-8 output on Windows. Check the rendered workbook
previews and import the changed examples with **Replace existing years** selected.
