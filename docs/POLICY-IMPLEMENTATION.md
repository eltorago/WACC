# Policy review pilot — implementation record

**23 September 2026.** This is a working engineering pilot. It is not a signed,
approved enterprise release.

## What changed

WACC now has a native Windows policy-review desktop and matching command-line
commands. They use one engine to read selected documents, record source passages,
save `.wacc` assessments, retain review decisions and export reports. The existing
web control library is preserved.

Users can select WA CSP, ASD ISM, AESCSF or any combination. The local collection
contains 86 WA requirements, 1,143 ISM controls and 354 AESCSF practices. AESCSF
domain/objective headings and the ISM catalogue's separate principles do not add
to those control counts. Reports calculate each framework's coverage separately
and can include only a selected subset of the frameworks in a saved assessment.

The WA training requirement, 3.2a, has two draft rule checks. All other requirements
support manual evidence review. Imported framework relationships never transfer
a finding to another requirement. No AI model or external analysis service runs.

Framework updates are explicit downloads from the official publisher sources.
They retain older copies, validate imports before activation and preserve saved
assessment versions. A changed WA source cannot silently inherit the training rule.
The signed corpus-package verifier remains separate from these local source imports;
publisher files cannot supply executable rules or change trusted keys.

## Reuse and implementation decisions

The existing Python framework registry, OSCAL and AESCSF loaders, identifiers,
source metadata and mappings were reused. The reviewed WA extraction approach was
adapted into the bounded parser worker. Its output was compared with every existing
WA requirement. Python/Tk was chosen for the desktop because the working code and
Python runtime were available; this host has no .NET SDK.

SQLite stores analysis snapshots and separate review events. Source files remain
external; retained text is configurable. Workers have a timeout and a Windows Job
Object memory/process limit. Schema checks, output escaping and atomic saves cover
the main input/output boundaries. The unsigned folder build bundles its runtime.
See [the architecture decision](adr/001-offline-policy-review.md).

## Validation actually performed

- Original repository baseline: **528 passed, 2 failed**, plus 19 historical plan
  corrections. The two failures were intermittent rejected-POST connection resets;
  bounded body consumption fixes that Windows server regression.
- The policy tests cover evidence spans, ambiguous wording, unrelated frequency,
  source status, corrupted SQLite, finalisation, retained history, report escaping,
  independent framework totals and framework-filtered exports.
- Update tests cover official-host restrictions, publisher-link selection,
  version retention, failed activation, changed files, concurrent writers and
  rejection of source-supplied rules.
- All seven non-empty selections of WA CSP, ISM and AESCSF were checked.
- The WA PDF parser reproduced all **86** existing requirement records with no
  changes to wording, context or section titles after whitespace normalisation.
- Live downloads: **WA CSP and ISM succeeded**. AEMO returned **HTTP 403**. Manual
  import of the existing AESCSF Core workbook succeeded; the latest online workbook
  bytes could not be independently downloaded in this environment.
- The frozen EXE imported the WA PDF, analysed all three frameworks, reopened and
  validated the saved assessment, and exported an ISM/AESCSF-only report.
  Analysis returned the documented exit code 7 for pilot limitations; import,
  saved-file validation and report export returned 0.
- Native desktop widget tests loaded a saved assessment and selected its evidence
  and framework relationships. These are functional checks, not visual or
  accessibility acceptance.

The full suite passed **578 checks with no failures**, plus 19 historical plan
corrections. One subsequent corrupt-cache recovery check was added; the final
focused-suite output is recorded alongside the full-suite log below.

## Delivery status against the refactoring brief

| Phase | Result and remaining gate |
|---|---|
| Repository assessment | Complete; working library and private source files preserved. |
| Deterministic analysis | Working for one actual WA requirement family. Independent rule approval and broader decomposition remain. |
| Persistence and CLI | Working snapshots, history, provenance, validation, export and review commands. Unknown earlier assessment schemas are rejected; no legacy `.wacc` schema was supplied for migration. |
| Desktop review | Functional native workflow. Screen-reader, high-DPI and visual acceptance remain. |
| Framework coverage | Selectable WA CSP, ISM and AESCSF, separate totals and filtered reports. Wider automated rules remain manual; AESCSF coverage is not a maturity-level calculation. |
| Source refresh | Publisher downloads and manual import work. AEMO's automated access restriction remains visible. |
| Enterprise packaging | Runnable unsigned folder with file inventory, hashes and dependency list. Managed installer, production signing and endpoint trust testing remain. |
| Pilot acceptance | Automated and synthetic tests completed. A permissioned real-policy benchmark, independent review and target-estate acceptance remain. |

## Local artefacts

Paths below are relative to the repository. Generated files and publisher text
stay in the ignored `data/local/` folder.

| Path | Contents |
|---|---|
| `data/local/offline-build/dist/wacc/wacc.exe` | Runnable desktop/CLI. Keep `_internal` alongside it. |
| `data/local/offline-build/release-manifest.json` | Payload file inventory and source revision. |
| `data/local/offline-build/SHA256SUMS.txt` | Payload hashes. |
| `data/local/offline-build/sbom.cdx.json` | Direct dependency list; full native SBOM reconciliation remains a release task. |
| `data/local/refactor-test-results.txt` | Full-suite validation output. |
| `data/local/policy-final-tests.txt` | Final policy/update checks after the corrupt-cache recovery change. |
| `data/local/framework-update-result.json` | Live publisher update results. |
| `data/local/framework-update-check/` | Isolated update-validation cache. |
| `data/local/frozen-three-framework.wacc` | Fictional training-policy assessment against all three frameworks. |
| `data/local/frozen-selected-frameworks.html` | ISM/AESCSF-only report from that saved assessment. |

## Screenshot limitation

The [plain-English README](policy-review/README.md) is written. Actual screenshots
are still outstanding. The Windows capture tool failed twice with
`SetIsBorderRequired failed: No such interface supported (0x80004002)`. The browser
tool also blocked opening the local report file. No mock screenshots were substituted.
Capture **Overview**, **Requirements** with the fictional training evidence, and
**Review finding** on a supported host to finish the illustrated guide.

## Not tested or approved

No clean-machine installation, enforced App Control/AppLocker test, managed
upgrade/uninstall, authenticated reviewer identity, full network-activity capture,
real-policy accuracy benchmark or independent accessibility evaluation was run.
No production binary or corpus signature has been created. The parser process
limits are not a complete operating-system sandbox. Full publisher content and
private assessments have not been added to Git.
