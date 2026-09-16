# WA Control Crosswalk

WA Control Crosswalk (WACC) is a local web application for exploring cybersecurity
controls across Australian and international frameworks, with a specific focus on Western Australian entities covered by the WA Cyber Security Policy (WA CSP).

This project pairs human-directed design with AI-assisted implementation. I selected the frameworks in scope, defined the four-step testing methodology applied to every control, the five-tier hierarchy, the regression self-test suite and reviewed and refined the output through iterative prompting. The code and control content were written using AI models, namely GPT-6 Astra, GPT-5.6 Sol and Claude's Opus 5.

It brings related requirements, assessment steps and publisher references together.

The application currently includes a workspace of **84 practical controls across 30
topics**. Each control has:

- a plain-English control statement and business risk;
- an ATT&CK assessment explaining relevant attack techniques and how the control helps;
- a **GRC** assessment covering documents, interviews, testing and expected results;
- a **Technical** assessment with short test steps, expected results and copyable commands;
- reviewed links to relevant publisher requirements; and
- links to other controls that address the same problem.

The source browser contains **7,395 records across 22 framework families (23 source sets)** when the reviewed sources are loaded. These include the ACSC mitigation strategies, SCF, Microsoft Cloud Security Benchmark v1 and CISA's Microsoft 365 baselines. You can search by
subject or identifier, inspect the source wording and published assessment material, move
between linked controls, limit results to selected frameworks and export mappings to CSV.

The Technical view provides **58 individual checks**, including **14 Active Directory
checks** informed by selected public PingCastle and Purple Knight criteria. Microsoft 365,
Entra ID and Windows checks include configuration evidence and practical test steps.
Thirteen dated WA Auditor General reports provide local audit context.

Commands are checked against official documentation and PowerShell 5.1/7 syntax, with
27 offline fixture cases. Live AD/M365/Azure behaviour must be tested in the target
environment. WACC displays instructions; it does not run them. GRC assessments name
specific documents to review, such as the supplier risk register for SC-02.
See [the assessment review](docs/assessment-method-review.md) for validation details.

The **Essential Eight is a subset of the 37 ACSC mitigation strategies**. WACC groups
them as one framework family. Mixed search results, workspace references and frequency
reports prefer Essential Eight maturity detail over the matching broad strategy row.
Both source editions remain directly accessible: February 2017 strategies and November
2023 maturity requirements. Raw record counts include both editions; they are not a
count of distinct controls. [ACSC describes the relationship here](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight).

Topics and controls are listed alphabetically. Open **Framework coverage & checks** in
the workspace to review new frameworks and navigate directly to a technical check.

## Run the application

WACC uses Python 3.9 or later and does not need third-party packages. From this repository
in PowerShell:

```powershell
python -m wacc sources
python -m wacc serve
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/) in a browser. The server is available
only on the local computer. See [HOW-TO-RUN.md](HOW-TO-RUN.md) for other commands and
troubleshooting.

The **Sources** page can download missing public documents and reload the corpus in one
step. It shows what is available, what has changed, and what needs a manual download.
For files already downloaded, `python -m wacc sources --import-from "C:\path\to\downloads"`
recognises reviewed copies by their contents and imports them under the expected names.

## Import department self-assessments

Open **Assessments** from the control workspace, or visit
[http://127.0.0.1:8765/assessments](http://127.0.0.1:8765/assessments).
The page compares annual assessments against the **WA Cyber Security Policy 2024**.
It shows a maturity trend, results for its six policy areas, and the evidence and actions
behind each requirement rating. Requirement links open the policy in the corpus;
related controls open their GRC and technical assessment methods.

To try it, select **Import the three examples**. The fictional Department of Silly Walks
improves from **1.00 / 4 in 2023** to **2.44 / 4 in 2024** and **3.70 / 4 in 2025**.
The 2023 workbook is a retrospective assessment against the 2024 criteria. All three
use the same departmental scope and 86 requirement rows.

To import your own assessment:

1. Download **Blank assessment template** from the page. The XLSX files are also in
   [examples/assessments](examples/assessments/).
2. On **Overview**, enter the department, assessment year and date, assessor and scope.
   Mark an assessment of a year before 2024 as retrospective. Record the accountable
   authority, approval date, Annual Implementation Report (AIR) status and reference,
   and exemption references in **Approval and reporting**. These fields are unscored.
3. On **Assessment**, complete the amber fields: rating, evidence reference or observation,
   owner, next action and due date. Keep the requirement IDs, prompts and column headings.
4. Choose **0 Not started**, **1 Planned**, **2 Partly implemented**, **3 Implemented** or
   **4 Tested and reviewed**. Ratings 3 and 4 require evidence. Use **Not assessed** for
   outstanding work, or **N/A** with an exclusion reason. Keep every requirement row.
   Include the relevant DGov exemption approval reference where applicable.
5. Save as `.xlsx`. Select one or more annual files on the Assessments page and click
   **Import selected files**. Each file may be up to 5 MB, with 20 MB and ten files per batch.
6. Select the department and year. Click a policy-area score or use the area filter to
   review its requirements. Selecting a year or area refreshes the results immediately.
7. To correct an imported department/year, edit the workbook and import it with
   **Replace existing years** selected. Importing the identical file again is harmless.

**How scores work:** this WACC scale tracks implementation and review progress; it is
not an official WA or Essential Eight maturity level. Scores are the equal-weight mean
of applicable requirement ratings. A missing rating leaves the score unavailable.
N/A rows are excluded. The trend uses the same applicable requirements across all years;
the policy-area table uses each year's applicable requirements and shows its exclusions.
WACC recalculates results from the ratings rather than trusting spreadsheet formula caches.
The policy prompts are authored summaries with stable references to the locally acquired
[2024 policy](https://www.wa.gov.au/system/files/2024-12/wacybersecuritypolicy.pdf).
Approval and reporting fields reflect page 22. For formal AIR submissions, use the
format prescribed by DGov.

**Where imports go:** assessed values and the workbook hash are stored in
`data/local/assessments/records.json`, which is excluded from Git and release packages.
Imports survive restarts. Keep the original XLSX files and back up this JSON file.
Set `WACC_ASSESSMENTS` before starting the server to use another private storage directory.
Only the fictional example files and blank template are included in the repository.
The local server has no user accounts or department-level access restrictions; protect
access to it and its storage before using real assessments in a shared deployment.

## How the repository is organised

| Path | Purpose |
|---|---|
| `wacc/` | Loads the corpus, finds controls, builds relationships and serves the web and command-line interfaces. |
| `data/library/` | The 84 locally written workspace controls, grouped into one JSON file per topic. |
| `examples/assessments/` | Blank WA policy assessment template and three fictional annual XLSX examples. |
| `data/department-assessment-policy.json` | Authored assessment prompts and references for 86 WA policy requirement records. |
| `data/local/assessments/` | Private imported assessments, excluded from Git and distribution. |
| `data/workspace-attack.json` | Local ATT&CK assessments for every workspace control, including explanations and MITRE mitigation references. |
| `data/workspace-technical*.json` | Check titles, access requirements, evidence, parent controls and publisher references. |
| `data/assessment-procedures.json` | The authoritative steps, commands, expected results and validation record for each technical check. |
| `data/assessment-sources.json` and `data/assessment-source-review.json` | Official command documentation and the recorded source review. |
| `data/workspace-grc-evidence.json` | Specific publisher-listed documents and practical review questions for all 84 controls. |
| `data/workspace-frameworks.json` | Reviewed links from workspace controls to additional source requirements. |
| `data/wa-audit-context.json` | Dated WA audit findings and their relevance to assessments. |
| `data/framework-review.json` | SCF mapping inventory and cloud framework priorities. |
| `data/corpus/` | Curated extracts used when a publisher does not provide a suitable machine-readable source. |
| `data/validation/` | Search expectations and the topic-frequency report used to check coverage and ranking. |
| `sources/acquisition.json` | Publisher download locations and instructions for sources that need manual acquisition. |
| `sources/permissions.json` | File hashes, source links, permissions and attribution evidence for reviewed documents. |
| `sources/files/` | Ignored local cache populated by `python -m wacc sources`; publisher files are not distributed with WACC. |
| `tools/` | Import and verification utilities used to rebuild or check parts of the corpus. |
| `docs/` | Framework coverage review and corpus revalidation, including proposed additional controls. |
| `tests/` | Regression checks for source permissions, loading, search, relationships, assessments and rendering. |

## How to read the results

Workspace controls, assessments and mappings are locally authored. Source links identify
the publisher requirement and the part addressed by the control.

Each workspace control also has a **MITRE ATT&CK** section. It names relevant Enterprise
techniques, links to MITRE, and explains whether the control reduces the likelihood of an
attack, helps detect or contain it, supports recovery, or enables another safeguard.
You can search the workspace by technique ID (for example, `T1110.004`), technique name,
or mitigation ID. Search by name requires the ATT&CK source to be loaded.

Mitigation references are checked against Enterprise ATT&CK 19.2. ATT&CK is a trademark
of The MITRE Corporation. See
[MITRE ATT&CK](https://attack.mitre.org/) for the publisher's technique descriptions.

The source browser preserves provenance, framework identity and hierarchy so readers can
return to the relevant publisher record. Source documents retain their own licences and
attribution. See [sources/README.md](sources/README.md) for automatic downloads, manual
acquisition and edition checks.

## Add a framework manually, from source to workspace

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
copy the structure in [the fictional example](tests/fixtures/onboarding-catalog.json):
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

## Check a change

Run the complete regression suite from the repository root:

```powershell
$env:PYTHONUTF8 = '1'
python tests\run_all.py
```

For changes to the Control workspace, the focused check is:

```powershell
python -m unittest tests.test_control_workspace tests.test_extended tests.test_terms
```

Run `python tools/revalidate_corpus.py` to check source hashes, corpus links and workspace
coverage. See [the revalidation report](docs/corpus-revalidation.md) for remaining source
limitations and seven proposed additional controls, and [the framework review](docs/framework-coverage-review.md)
for missing frameworks and acquisition considerations.

See [the repository review](docs/repository-review.md) for completed improvements and
the next maintenance priorities.
