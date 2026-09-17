# Add a framework from source to workspace

Run the commands in this guide from the repository root. See [source acquisition](README.md) for existing sources.

Adding a new framework currently involves editing the source catalogue, registering a
loader and reviewing its workspace mappings. Downloading a file alone does not import
controls. The workflow below uses WACC's existing OSCAL loader; a publisher spreadsheet
or unusual document layout may need its own loader instead.

### 1. Choose the edition and obtain the source

Record the publisher, title, edition/date, download URL, control count and reuse terms.
Use a stable short key such as `example-fw`; keep that key across its records and mappings.
If the material is a subset or profile of an existing framework, add its relationship in
`wacc/framework_families.py` so coverage does not count it as an independent framework.

Save the reviewed original under `sources/files/`. For a source already in the catalogue:

```powershell
python -m wacc sources --only "publisher-file.json"
# Or import a manually downloaded reviewed copy:
python -m wacc sources --import-from "C:\Downloads" --only "publisher-file.json"
```

For a new source, obtain it from the publisher first. Calculate its exact size and hash:

```powershell
Get-Item -LiteralPath 'sources/files/example-framework-1.json' | Select-Object Name,Length
Get-FileHash -LiteralPath 'sources/files/example-framework-1.json' -Algorithm SHA256
```

Add one entry to `sources/permissions.json` under `files`. Use the actual reviewed values:

```json
{
  "filename": "example-framework-1.json",
  "status": "local-reference-only",
  "policy_group": "example-publisher",
  "license": "Actual licence or local-use terms",
  "permission_url": "https://publisher.example/terms",
  "basis_and_conditions": "Record the permitted use and required attribution.",
  "source_url": "https://publisher.example/framework",
  "sha256": "replace with the 64-character SHA256",
  "bytes": 12345,
  "reviewed_on": "YYYY-MM-DD",
  "modified": false,
  "provenance": "Downloaded from the publisher; edition checked against its release page."
}
```

Add the same filename to `sources/acquisition.json`. Choose one acquisition method:

```json
{"filename":"example-framework-1.json","method":"automatic","urls":["https://publisher.example/download/catalog.json"]}
```

```json
{"filename":"example-framework-1.json","method":"manual","instructions":"Sign in to the publisher portal, export edition 1 as JSON, and save it as example-framework-1.json in sources/files/."}
```

Both catalogue files must contain the same filenames. The downloader checks the reviewed
hash; a changed publisher file needs a new edition/content review before updating it.
Keep publisher originals and restricted extracts out of Git.

### 2. Prepare structured control records

Use a publisher OSCAL catalog directly where available. For a manual transcription,
copy the structure in [the fictional example](../tests/fixtures/onboarding-catalog.json):
`catalog.metadata` holds the edition; `catalog.controls` contains an `id`, `title` and
`parts` for each requirement. Put the exact requirement in a part named `statement`.
Preserve headings, applicability, parent relationships, tables and assessment wording.
Retain page/section references in the extraction record so another reviewer can check it.

Keep the original document as a separate catalogue entry. Record the derived JSON's own
hash and describe the transcription in its `provenance`, with `modified: true` and manual
acquisition instructions that explain how to recreate it. Do not label a local test as a
publisher `assessment-method`: that field is for the publisher's actual procedure.

Preview an OSCAL file before connecting it to the application:

```powershell
python tools/validate_framework.py sources/files/example-framework-1.json --key example-fw --expect-controls 100
# Reproducible demonstration using the repository's fictional one-control fixture:
python tools/validate_framework.py tests/fixtures/onboarding-catalog.json --key example-fw --expect-controls 1 --assessment-publisher "Example publisher"
```

The preview prints imported counts, normalised UIDs and problems. It fails on an empty
catalog, missing statement text, duplicate identifiers or an unexpected count. It checks
WACC import compatibility; compare the text and count with the publisher separately.

For XLSX, HTML or PDF sources, add a format-specific loader under `wacc/loaders/`, using
`extended.py` as an example. Extract complete statements and reject changed table layouts.
Keep extraction scripts under `tools/`; keep unreviewed output in ignored `data/review/`.

### 3. Register the framework and connect its loader

In `wacc/registry.py`, add a `Framework` **before** `FRAMEWORKS_BY_KEY` is created. For example:

```python
FRAMEWORKS.append(Framework(
    key='example-fw', name='Example framework', short_name='Example',
    publisher='Example publisher', jurisdiction=Jurisdiction.INTERNATIONAL,
    tier=Tier.CATALOGUE, fidelity=Fidelity.CURATED_EXTRACT,
    licence=Licence.IMPORT_ONLY, levels=_levels('Control'),
    revision='1.0', revision_source='Publisher release heading',
    source_file='example-framework-1.json',
    source_url='https://publisher.example/framework',
    attribution='Actual publisher attribution',
))
```

Choose the actual jurisdiction and source type. Use `OFFICIAL_MACHINE_READABLE` for an
unaltered publisher OSCAL export, `CURATED_EXTRACT` for a reviewed transcription, and
`IMPORT_ONLY` for local-only text. `SHIPPABLE` applies only to extracts cleared for
distribution. Framework tiers describe statute, mandated policy, outcome/maturity,
catalogue or technical specification; they do not determine workspace topic order.

In `wacc/build.py`, inside `build()` and before the final unloaded-framework loop:

```python
fw = corpus.frameworks['example-fw']
path = _doc(fw.source_file)
if _exists(path):
    report.record(fw.key, oscal.load_into(corpus, fw, path))
else:
    report.skip(fw.key, 'Source not present; run python -m wacc sources')
```

If the file includes genuine publisher assessment methods, pass
`assessment_publisher='Publisher and assessment edition'` to `oscal.load_into`.
For a new file format, import and call your loader here instead. Add the framework's
usual name/abbreviation to `NAMED_SETS` in `wacc/terms.py`, for example
`'example framework': ('example-fw', None, 'the Example framework')`.

Run `python -m wacc build`, then search the exact UID printed by the preview, such as
`example-fw:ex-1`. Identifiers are normalised, so use the loaded UID in mappings.

### 4. Link requirements to workspace controls

Add reviewed entries to the relevant control in `data/workspace-frameworks.json`:

```json
"PA-01": [
  {
    "uid": "example-fw:ex-1",
    "relationship": "Partially addresses",
    "provenance": "Locally reviewed mapping",
    "basis": "Privileged-access approval records support the quarterly review."
  }
]
```

Append to existing arrays; do not replace their other mappings. Use `Directly addresses`,
`Partially addresses` or `Related only` and explain the actual overlap. The new framework
then appears in workspace scope, search, source navigation and mapping exports.
Publisher-provided crosswalks belong in the loader as `Link` objects with their publisher,
edition and provenance. Do not relabel a local mapping as published.

If the requirement needs a new practical control, add it to the appropriate
`data/library/*.json` file with a unique ID, title, statement, risk, scope, examine,
interview, test, test_steps, expected, related and mappings. Use an existing control as
the schema example. New topics also need a phrase definition in `tools/analyse_topics.py`.
New controls need GRC evidence, technical-check parents and an ATT&CK assessment; reuse
existing checks where the test is the same.

### 5. Add or revise the assessments

For **GRC**, edit the workspace control's document, interview, test and expected-result
fields. Name the actual records to inspect. In `data/workspace-grc-evidence.json`, point to
the relevant published Examine procedure using `source_uid` and `published_ref`; its
`documents` must occur in that procedure. Describe the local review in `application`.
If the new framework has no published assessment method, keep a relevant existing corpus
procedure as support and put local document choices in the control's `examine` field.

For **Technical**, update or add a check in `data/workspace-technical.json`,
`workspace-technical-ad.json` or `workspace-technical-cloud.json`. It needs:

- a unique check ID, title, platform and `parents` workspace IDs;
- a short purpose (`statement`), access requirements (`prerequisites`) and `artifacts`;
- official source keys from that file's `sources` table, and corpus UIDs in `references`.

Add the matching ID to `data/assessment-procedures.json`. This is the single place for
`command`, `run_steps`, `decision`, `limits`, console `profile`, command `sources` and
`validation`. Include `scopes` for Graph permissions and `inputs` for required exports.
Write three short steps where possible: inspect configuration, exercise the permitted
and prohibited cases, and check the resulting events. State a measurable expected result.

Add official command references to `data/assessment-sources.json` with `title`, `url`
and `verify_terms`. Then review and validate them:

```powershell
python tools/review_assessment_sources.py
powershell.exe -NoProfile -File tools/validate_assessment_commands.ps1 -OutputPath data/review/commands-ps51.json
pwsh -NoProfile -File tools/validate_assessment_commands.ps1 -OutputPath data/review/commands-ps7.json
python tools/check_assessment_doc_parameters.py
powershell.exe -NoProfile -File tests/test_assessment_commands.ps1
pwsh -NoProfile -File tests/test_assessment_commands.ps1
```

Use your organisation's approved script execution policy. The parser checks syntax; the
parameter checker checks documented parameter names. Add offline fixtures for important
decisions, including errors and empty inputs. Run behaviour tests in a representative
lab and record what actually ran, platform/module versions and results in `validation`.
Set `command_sha256` to SHA256 of the exact UTF-8 command string after review. Copy the
reviewed retrieval metadata from `data/review/assessment-sources/retrieval.json` into
`data/assessment-source-review.json` under `sources`; preserve its top-level method/date.

### 6. Validate the complete import and inspect it in the browser

Add regression cases for exact wording, expected record count, duplicate IDs, missing
source behaviour, assessment provenance, scope filtering and navigation. Update explicit
inventory counts in tests and documentation when adding records or checks.

```powershell
$env:PYTHONUTF8 = '1'
python tests/run_all.py
python tools/revalidate_corpus.py
python tools/analyse_topics.py
python -m wacc.packaging
```

Resolve new errors and review warnings. Restart `python -m wacc serve` after code or
assessment-data edits; the Sources page reloads the corpus after source downloads.
Search the new framework and an exact UID. Open a mapped workspace control, toggle GRC
and Technical, follow its source link and export its mappings. Turn the framework off
and confirm its references disappear. Check that related framework editions are grouped
and overlapping strategies are not counted twice.

Commit reviewed code, mappings, tests and documentation. Exclude publisher files,
restricted extracts, credentials and organisation-specific assessment evidence. Review
`git diff` and the packaging result before pushing the branch and opening a pull request.
