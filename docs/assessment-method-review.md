# Assessment review

Reviewed 16 September 2026: all **58 technical checks**, their use across **84 workspace
controls**, and the document references for every GRC assessment.

## Content and presentation

Technical instructions, expected results and interpretation notes were reduced from
9,339 words to about 3,860 words (59%). Most checks now have three steps. AP-01 retains
six steps to cover WDAC, AppLocker, MDM, file types and event interpretation.

Steps and expected results appear first. Console setup is shown once per assessment
page; commands, evidence and sources expand when needed. Repeated disclaimers were
removed from Technical, GRC, ATT&CK, OAG context and source-reference sections.
The old technical procedure copies were removed from `workspace-technical*.json`;
`assessment-procedures.json` is now their single source.

## Corrections found during command review

| Check | Correction |
|---|---|
| TECH-CRYPTO | Added Azure setup and separate Windows/Azure execution branches, so each console needs only its own modules. |
| TECH-MACROS | Setup explicitly uses the standard test user's session for HKCU and user policy. |
| AD-CHECK-10 / 12 | Read `nTSecurityDescriptor` from the selected DC instead of relying on the current `AD:` provider connection. |
| TECH-BASELINE | Normalise JSON object-property order before comparing policies; real state changes still appear. Array order remains visible for review. |
| TECH-EMERGENCY | Collect `onPremisesSyncEnabled` for the cloud-only account review. |
| TECH-ASR | Filter null rule/action entries so an empty configuration does not produce a fictitious null rule. |
| Graph collections | Reject null, scalar and object-shaped `value` responses as malformed collections. Preserve paging and permission failures. |
| TECH-PHYSICAL | Reject unknown event-result values instead of silently skipping them. |

Material platform details remain in the tests: CiTool active versus audit mode,
AppLocker's CSP limitation, SMTP AUTH inheritance, site-property collection, audit
search caps, OS defaults and KRBTGT reset evidence.

## Validation

| Review | Result |
|---|---|
| Official references | All 107 Microsoft documentation pages retrieved; URLs, hashes and review dates recorded in `data/assessment-source-review.json`. |
| Command parameters | 58 documented cmdlets checked against reference syntax; no unmatched named parameters. |
| PowerShell syntax | All 58 examples parsed in Windows PowerShell 5.1.19041.6456 and PowerShell 7.6.5. |
| Offline behaviour | 27 fixture cases passed in both engines: Graph paging/errors, SMTP inheritance, credential lifetime, badge validity, findings, supplier expiry, JSON comparison, DC selection and encryption branches. |
| GRC source matching | All 84 document selections match their published NIST SP 800-53A Examine procedures. SC-02 retains its specific supplier risk-register review. |
| Regression | Full suite: 494 passed, zero failed, 19 recorded plan corrections. Corpus and packaging checks: zero problems. |
| Import guide | The [framework import example](../sources/add-framework.md) imports one control and one published assessment; tests reject duplicate IDs, missing text, empty files and wrong counts. |

These are documentation, syntax and offline checks. Live AD, Microsoft 365 and Azure
behaviour has not been tested against an organisation's environment. The application
provides the steps needed to do that. Record the target, scope, module/OS version,
expected outcome, actual result and supporting event IDs when running them.

## Essential Eight and ACSC strategies

[ACSC identifies the Essential Eight as a subset of its mitigation strategies](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight).
WACC now counts one framework family, with two source editions: the 37 strategies from
February 2017 and 304 maturity-detail records from November 2023.

Mixed results prefer maturity detail over the corresponding eight broad strategy rows.
Exact source links still open every original record. A maturity record links back to
its broader strategy. Scope settings can select either edition, and frequency reports
group the family and remove the overlapping broad rows. Searching `E8` now opens the
maturity model instead of the ISM's maturity tags.

## Reproduce

```powershell
python tools/review_assessment_sources.py
powershell.exe -NoProfile -File tools/validate_assessment_commands.ps1 -OutputPath data/review/commands-ps51.json
pwsh -NoProfile -File tools/validate_assessment_commands.ps1 -OutputPath data/review/commands-ps7.json
python tools/check_assessment_doc_parameters.py
python tests/test_assessment_procedures.py
python tests/run_all.py
python tools/revalidate_corpus.py
python tools/analyse_topics.py
python -m wacc.packaging
```

Use the organisation's approved execution policy. This review used process-only
RemoteSigned for the locally authored scripts. Documentation downloads are not executed.
