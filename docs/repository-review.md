# Repository review — 16 September 2026

The review covered source acquisition and permissions, loaders and registry, search and
counts, workspace content, rendering, validation tools, tests and operating documentation.

## Improvements completed

| Area | Finding and change |
|---|---|
| Technical assessments | Rewrote all 58 procedures in shorter language; removed duplicate procedure fields and repeated setup text. Corrected command issues listed in the [assessment review](assessment-method-review.md). |
| GRC and risk context | Kept specific documents and review actions, removed repeated qualification paragraphs, and shortened vague backup/remediation results and mapping explanations. Publisher requirement text remains intact. |
| Framework overlap | Modelled Essential Eight as part of the ACSC strategy family; updated workspace references, topical search, exports, frequency analysis and framework counts. Preserved source editions and exact navigation. |
| Search | Fixed the stale `E8` alias; added names for the ACSC strategies. Excluded internal execution/validation metadata from workspace search. |
| Framework onboarding | Added the full README workflow, a local OSCAL preview tool and an executable fictional example with rejection tests. |
| Test quality | Removed minimum prose-length rules that encouraged padding. Added import and family-overlap regression cases and expanded the command fixtures from 16 to 27. |
| Test reporting | Count unittest results in the combined total and show failure locations; suites no longer appear as zero tests despite running assertions. |
| Source maintenance | Documentation reviews use the actual run date instead of a hard-coded date. Refreshed all 107 command references and the corpus/frequency reports. |
| Browser usability | Setup links open the relevant instructions. Copy buttons select the command text immediately so Ctrl+C works when automatic clipboard access is unavailable. |

## Further improvements identified

1. **Test commands in representative environments.** Maintain disposable Windows/AD and
   Microsoft 365/Azure test environments for module versions, roles, licence-dependent
   behaviour and the permitted/denied cases. The offline suite cannot verify these.
2. **Separate portable tests from full-corpus tests.** Several older suites require locally
   acquired publisher files. A clean-checkout suite with small synthetic fixtures would
   support CI, while a second job could validate a reviewed private source cache.
3. **Centralise framework registration.** Registry definitions, loader dispatch and search
   aliases are still separate edits. A declarative framework manifest could make future
   imports less repetitive; the README documents the current working path.
4. **Track edition changes at requirement level.** Source hashes detect changed files.
   A reviewed diff of added, removed and changed requirements would make mapping and
   assessment updates easier to target.
5. **Split broad cloud checks as coverage grows.** Backup, encryption, inventory and
   network checks currently span several platforms. Keep their collection limits clear
   and add service-specific examples when a representative environment is available.

Manual import instructions are in the
[README](../README.md#add-a-framework-manually-from-source-to-workspace).
