# Assessment method review

Reviewed 16 September 2026. The workspace retains 84 practical controls and 58 individual
technical checks. Shared checks appear under each relevant control. This review covers
all of them, including the 14 AD checks and five additional Entra/Microsoft 365 checks.

## What changed

The Technical view now gives the required console/module and access, input records,
copyable collection commands, detailed execution steps, expected behaviour and limits.
Each check distinguishes configuration evidence from a positive/negative behaviour test.
Queries never run from the application, and no tenant connection or scanner is added.

AP-01 explains how to inspect deployed WDAC/App Control policies with CiTool, distinguish
an active policy from audit/enforce settings, reconcile policy IDs and loaded-policy
events, and test reviewed benign allowed and unapproved code. The AppLocker path exports
effective GPO/local XML, checks collection modes, predicts decisions for a representative
user with Test-AppLockerPolicy, and then corroborates actual execution using event logs.
Microsoft's documented AppLocker CSP limitation has its own MDM verification path.
Script-host restrictions, DLL/installer scope, and audit events are not presented as
equivalent to a blocked executable.

Every GRC control names specific documents found in a published NIST SP 800-53A Examine
procedure already loaded in the corpus. WACC adds practical review questions, with
source navigation and a runtime check that the names still occur in the loaded procedure.
These are evidence recommendations, not a claim that NIST requirements automatically
apply to WA entities or that the reference covers the entire practical control.

For SC-02, SR-3 explicitly lists **risk register documentation**, acquisition contracts
and a supply-chain risk-management plan. The assessment now follows a provider's risk ID
through due diligence, ratings, contract controls, treatment owner/deadline, residual-risk
acceptance and reassessment. Where an artefact name is a local choice, such as a macro
register or a general risk-treatment register, the text says so. Source-specific incident
reporting clocks remain grounded in the existing WA/legislative mappings, not NIST.

## Validation performed

| Check | Result and limit |
|---|---|
| Official command/API references | 107 Microsoft documentation pages retrieved successfully. Reviewed command/API paths, access requirements and relevant interpretation; recorded URLs and document hashes. |
| Parameter spelling | 59 documented cmdlets cross-checked against their reference syntax; no unmatched named parameters. This is not a live service parameter-set test. |
| PowerShell syntax | All 58 examples parsed without errors in Windows PowerShell 5.1.19041.6456 and PowerShell 7.6.5. |
| Offline execution | 16 fixture cases passed in both engines. They test Graph paging, access/schema failures, unsafe/repeated nextLink, SMTP inheritance, credential lifetime, badge validity, finding closure and supplier expiry/duplicates. They do not emulate a whole tenant or AD forest. |
| Local Windows collection | Five read-only calls succeeded: OS CIM, SMB server configuration, Defender ASR preferences, DeviceGuard CIM and Spooler-service CIM. Only success and output shape were recorded; this is not a DC or enforcement test. |
| App Control/AppLocker on this host | CiTool and AppLocker cmdlets were unavailable. Their official syntax and procedures were reviewed; no local policy deployment or allow/deny test is claimed. |
| GRC evidence | All 84 document selections match the actual published Examine statement and reference in the corpus. |
| Application regression | Full suite clean: 426 counted checks plus unittest suites. Corpus integrity and packaging checks reported zero problems. Browser checks confirmed command copying, GRC source navigation and ACSC strategy search. |
| Target-environment behaviour | Not performed. AD, Entra, Microsoft 365, Azure, PKI, OT, backup, physical-access and deployment tests need the actual authorised environment and evidence. The workspace shows this limit per check. |

Do not score a missing module, access-denied query, empty/unreconciled population, capped
search, absent property or unperformed negative test as passing. The scripts stop on
errors where possible; the assessor still needs to inspect completeness and applicability.
Read-only collection can reveal sensitive metadata, so keep exports in the organisation's
approved assessment location. The app stores no submitted tenant evidence or credentials.

For each environment, record tenant/domain/device and sample scope, module/OS version,
collection time, expected result, actual output and matching event/ticket references.
Complete the positive and negative steps before accepting a control. Use an approved
test environment for state-changing exercises; collection scripts do not perform those
changes. A successful query does not establish that a security control is effective.

## ACSC mitigation framework

The corpus now imports all **37 strategies in five categories** from the official
[Strategies to Mitigate Cyber Security Incidents](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/mitigating-cyber-security-incidents/strategies-to-mitigate-cybersecurity-incidents)
table, together with the matching sections in the
[Mitigation details](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/mitigating-cyber-security-incidents/strategies-to-mitigate-cyber-security-incidents-mitigation-details).
Both pages are acquired automatically and cached locally; publisher files are not hosted
or committed. Source wording is preserved with ASD/Commonwealth attribution under the
publisher's CC BY 4.0 terms.

The edition is February 2017, despite newer attachment hosting dates. Deprecated product
examples and historical thresholds are retained as source text and labelled. S01–S37
are WACC row locators. Every strategy has a reviewed partial link to at least one practical
control; those links are WACC analysis, not a published ASD crosswalk.

## Reproduce the review

Run `python tests/test_assessment_procedures.py` for source matching, framework coverage,
rendering and the offline PowerShell checks when PowerShell is installed. Run
`python tests/run_all.py` for the complete application regression suite, and
`python tools/revalidate_corpus.py` for source/corpus/mapping integrity.

For command-reference maintenance:

```powershell
python tools/review_assessment_sources.py
powershell -NoProfile -File tools/validate_assessment_commands.ps1 -OutputPath data/review/commands-ps51.json
python tools/check_assessment_doc_parameters.py
powershell -NoProfile -File tests/test_assessment_commands.ps1
```

Run locally authored scripts under your approved PowerShell execution policy. The review
used a process-only RemoteSigned policy, with no machine/user policy changed. The
reference-refresh command downloads documentation only; it never executes downloaded code.
Updating a document hash alone does not approve changed procedures or examples.
