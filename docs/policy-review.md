# Offline policy coverage review

For a step-by-step introduction, start with the
[plain-English desktop guide](policy-review/README.md).

This is an engineering pilot. It compares selected policy text with requirements;
it does not establish that controls operate effectively or that an organisation
complies with the framework.

## Run from source

Use Python 3.13 on Windows for the tested development configuration. From the
repository root, install the pinned development dependencies into an approved
environment, then open the desktop:

```powershell
python -m pip install -r requirements-policy.txt
python -m wacc open
```

Dependency installation is a build/setup activity. Analysis, review and exports do
not fetch dependencies or sources. The existing control library still starts with
`python -m wacc serve`.

Select **New assessment**, enter a name and explicit scope, choose documents and
their approval status, then select WA CSP, ASD ISM, AESCSF, or a combination.
The editions and source/extract hashes are saved in every run.

The pilot imports **86 WA policy requirement records**. The automated rule family
currently covers **3.2a, annual cyber security awareness training**. It has two
draft atoms: a personnel-training commitment and annual frequency. The remaining
requirements are available for manual review and stay NotAssessed automatically.
ISM and AESCSF can each be used independently of WA CSP. Their controls and
practices support manual review. AESCSF domains and objectives are retained as
context, not counted again as practices. The CLI also retains its optional
Essential Eight and NIST CSF imports. Coverage is calculated separately for each
selected framework, using its own requirements and review decisions.

## Prepare the local baseline

Open **Framework updates**, select the frameworks you need and choose
**Download updates**. The command-line equivalent is:

```powershell
python -m wacc corpus update --format json
python -m wacc corpus update --framework ism --format json
```

This is the only assessment workflow that downloads files. WA CSP is discovered
on its official 2024 publication page; AESCSF Core is discovered on AEMO's resources
page; ISM comes from ASD's official OSCAL mirror. HTTPS redirects must stay on the
configured publisher hosts. Updates do not upload policy documents.

Each file is parsed in a bounded worker before activation. The update preserves
older versions and atomically changes the current-version index. Failed downloads
or parsing leave the previous version active. A reduction of more than 20% in
requirements needs investigation rather than automatic activation. Source updates
import requirements and published links, never executable rules or trusted keys.
The draft training check is used only with its reviewed source fingerprint and
matching requirement text; other imported requirements remain manual.

Updates are stored in `%LOCALAPPDATA%\WACC\frameworks`. `WACC_FRAMEWORK_CACHE`
can select a different local folder. They take precedence over the prepared local
library for new runs. Saved assessments contain their original requirement snapshots.
Use `--corpus-version 2026.09.23-pilot.2` to explicitly select the original prepared
library rather than active local updates.

If automated access is blocked, open the publisher page shown in the error and
download the relevant file. Select that framework alone and choose **Import
framework file**, or run:

```powershell
python -m wacc corpus update --framework aescsf --import-file "C:\Downloads\the-aescsf-v2-core.xlsx" --format json
```

A manual import records that the latest online version was not verified. On
23 September 2026 the live update checks downloaded WA CSP and ISM successfully;
AEMO returned HTTP 403. The AESCSF manual-import path was verified against the
existing local Core workbook.

## Review and save

The requirement list uses the actual source section references. Select a row to
see its authoritative wording, atoms, automated status and evidence. Choose a
passage to see the recorded source locator and highlighted rule-triggering spans.
DOCX is extracted text, not Word pagination; PDF locators identify pages without
claiming bounding boxes.

**Review finding** stores a separate event. Select the obligations you confirmed
and the evidence you accept, or link another retained passage. A Covered decision
requires every obligation and supporting evidence. Rejected evidence remains in
the automated history. Reasons and a reviewer name are required; names are
self-declared, not authenticated identities.

**New analysis run** changes document selection while preserving earlier runs.
Use it to exclude or replace a document. Earlier review decisions become
NeedsReReview. **History** opens old results without rebuilding the corpus.
**Finalise snapshot** blocks further review of the current run through WACC; it
does not prevent external database editing. Create a new analysis to revise it.

## Retention and source links

- **evidence** (CLI default): source paths, hashes and candidate passages, including
  ambiguous/contradictory passages. Other extracted text is discarded.
- **extracted** (desktop default): retains every extracted passage for broader manual inspection.

Both modes contain sensitive text. Neither embeds originals or encrypts SQLite.
Use approved local storage. Original source files remain untouched. Before opening
an original, WACC compares its hash; a changed file cannot supply an old locator.

The parser accepts UTF-8 TXT/Markdown, macro-free DOCX and text PDFs. Image-only
PDF pages, excluded DOCX content, encrypted files, malformed inputs and parser
failures stay visible. Incomplete selected documents prevent an ordinary complete
coverage finding. No OCR, Office automation or external document content is run.

Limits: 250 selected documents; 16 MiB input each; 300 PDF pages; 2 million
extracted characters per document; 8 million per selected scope; 30-second parser
timeout; 256 MiB worker memory and one-process Windows Job Object limit. Archive entry,
decompression and XML-depth limits also apply. The worker is process-separated,
but is not a hardened OS sandbox.

## CLI workflow

```powershell
python -m wacc frameworks --format json
python -m wacc analyse "C:\Policies" --recurse --scope "Approved IT policies selected for September review" --document-status approved --retention extracted --assessment ".\Review.wacc" --format json
python -m wacc analyse "C:\Policies" --recurse --framework wa-csp --also-assess ism --also-assess aescsf --scope "Selected approved policies" --document-status approved --retention extracted --assessment ".\Three-framework-review.wacc" --format json
python -m wacc requirements ".\Review.wacc" --format json
python -m wacc evidence ".\Review.wacc" --requirement "wa-csp:3.2a" --format json
python -m wacc gaps ".\Review.wacc" --format json
python -m wacc validate ".\Review.wacc" --format json
python -m wacc report ".\Review.wacc" --format html --output ".\Review.html"
python -m wacc report ".\Review.wacc" --format csv --summary-only --output ".\Review.csv"
python -m wacc report ".\Three-framework-review.wacc" --framework ism --framework aescsf --format html --output ".\ISM-and-AESCSF.html"
python -m wacc snapshot ".\Review.wacc" ".\Review-copy.wacc"
python -m wacc open ".\Review.wacc"
```

Use `--framework ism` or `--framework aescsf` to assess either framework by itself.
`--framework-version` can pin the displayed edition. Local update versions are
pinned in each saved run; a request for a no-longer-active local corpus version
fails rather than substituting new content. `--also-assess csf` requests independent manual target review.
`--run <id>` selects a saved historical run for inspection/reporting.
`review --help` describes headless review, including `--link` for manual evidence.

JSON writes exactly one JSON value to stdout; errors go to stderr. Exit codes:
0 complete, 2 invalid arguments, 3 input/assessment error, 4 unexpected failure,
5 corpus/trust error, 6 output/lock error, 7 completed with material limitations,
130 cancelled. The pilot's analyses return 7 because rule approval and broad
automation remain incomplete. Low coverage itself is not an execution error.

```powershell
$json = & python -m wacc analyse "C:\Policies" --scope "Selected policies" --format json
$code = $LASTEXITCODE
if ($code -ne 0 -and $code -ne 7) { throw "WACC failed: $code" }
$result = ($json -join [Environment]::NewLine) | ConvertFrom-Json
$result.requirements | Where-Object automatedFinding -eq 'NoEvidenceFound'
```

## Method and versions

Every bounded passage receives a complete same-sentence lexical scan; there is no
top-K cut-off. Rule phrases and a fixed allowlist of patterns produce source spans
and trace checks. The rule language has `all`, `any`, `phrases` and named `pattern`
operators. Other operators fail validation. There is no corpus-supplied regex,
Python, SQL, shell, template execution or arbitrary expression evaluation.

No cross-sentence implication, general contradiction analysis, date precedence,
acronym inference, or quantitative confidence is claimed. Contradiction detection
is limited to documented explicit negative phrases within the supported family.
Draft/unknown document status, advisory language, exceptions and quoted/background
context cannot produce an ordinary FullCandidate. A missing annual qualifier leaves
the training requirement partial; a frequency attached to tickets cannot fill it.

Counts use source requirements, not containers. Computable requirements contribute
equal weight; atom completeness is calculated within each requirement. Unknown
requirements remain in the completeness denominator. Reviewer-confirmed evidence
is separate. N/A is used for empty denominators. Mapped relationships contribute no
direct coverage. Duplicate file hashes are included once and reported explicitly.

## Corpus packages

`corpus verify` and `corpus install` validate signed `.waccpack` files. The archive
contains exactly `manifest.json`, `corpus.json` and `signature.json`. Verification
checks an installation-owned Ed25519 key, payload hashes, engine compatibility,
record bounds and the finite rule language. Packages cannot supply trusted keys.
Installed versions go to `%LOCALAPPDATA%\WACC\corpus`; selecting one requires its
explicit version. Source-file refreshes are a separate local import path with no
downloaded rules.

The shipped trust file is intentionally empty: no approved production signer was
provided. The development baseline is labelled a pilot and is not a signed corpus.
There is no UI switch to ignore package signatures.

## Tests and remaining acceptance work

```powershell
python tests/test_policy_review.py
python tests/run_all.py
python tools/build_policy.py
```

See [deployment notes](deployment/POLICY-PILOT.md) for the actual executable,
storage/process inventory and release blockers. A production claim additionally
requires independent rule approval, permissioned held-out policies, accessibility,
representative parser stress testing and clean managed-endpoint tests.
