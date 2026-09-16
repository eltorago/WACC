# WA Control Crosswalk

WA Control Crosswalk (WACC) is a local web application for exploring cybersecurity
controls across Australian and international frameworks, with a specific focus on Western Australian entities covered by the WA Cyber Security Policy (WA CSP).

This project pairs human-directed design with AI-assisted implementation. I selected the frameworks in scope, defined the four-step testing methodology applied to every control, the five-tier hierarchy, the regression self-test suite and reviewed and refined the output through iterative prompting. The code and control content were written using AI models, namely GPT-6 Astra, GPT-5.6 Sol and Claude's Opus 5.

It brings related requirements together without hiding the original source text
or treating a crosswalk as proof of compliance.

The application currently includes a workspace of **84 practical controls across 30
topics**. Each control has:

- a plain-English control statement and business risk;
- an ATT&CK assessment explaining relevant attack techniques and how the control helps;
- a **GRC** assessment covering documents, interviews, testing and expected results;
- a **Technical** assessment with platform-specific checks, artefacts, collection examples and interpretation limits;
- reviewed links to relevant publisher requirements; and
- links to other controls that address the same problem.

The wider source browser contains **7,395 records from 23 frameworks** when the reviewed sources are loaded. These include the ACSC's 37 Strategies to Mitigate Cyber Security Incidents, SCF, the Essential Eight, Microsoft Cloud Security Benchmark v1 and CISA's Microsoft 365 baselines. You can search by
subject or identifier, inspect the source wording and published assessment material, move
between linked controls, limit results to selected frameworks and export mappings to CSV.

The Technical view provides **58 individual checks**, including **14 Active Directory
checks** informed by selected public PingCastle and Purple Knight criteria. Microsoft 365,
Entra ID and Windows checks include configuration evidence and practical test steps.
WACC does not run these checks or reproduce vendor scanners and scores. Thirteen dated
WA Auditor General reports provide local context without treating historical findings as
current findings about an organisation.

Every technical check includes PowerShell collection examples, access requirements,
execution steps and interpretation. The examples were checked against official Microsoft
documentation and parsed in PowerShell 5.1 and 7, with selected offline fixtures and local
Windows reads. Each check states what still needs validation in the target environment;
WACC does not claim a live AD or Microsoft 365 test has run. Every GRC assessment also
names specific documents from the corpus and explains what to verify in them. For example,
SC-02 links supplier risk-register documentation to NIST SP 800-53A's SR-3 assessment.
See [the assessment review](docs/assessment-method-review.md) for scope and validation.

The ACSC strategies retain their **February 2017** edition and companion implementation
guidance. Historical products and thresholds are labelled; current ISM and Essential Eight
requirements remain separate.

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

## How the repository is organised

| Path | Purpose |
|---|---|
| `wacc/` | Loads the corpus, finds controls, builds relationships and serves the web and command-line interfaces. |
| `data/library/` | The 84 locally written workspace controls, grouped into one JSON file per topic. |
| `data/workspace-attack.json` | Local ATT&CK assessments for every workspace control, including explanations and MITRE mitigation references. |
| `data/workspace-technical*.json` | Individual technical assessments and their publisher references. |
| `data/assessment-procedures.json` | How to run all 58 technical checks, including commands, prerequisites and validation limits. |
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

The workspace controls and their assessment methods are locally authored. Their source
links describe reviewed overlap with publisher requirements. A linked requirement may
address all of a control, only part of it, or provide related context. Meeting a workspace
control therefore does not automatically meet every linked framework requirement.

Each workspace control also has a **MITRE ATT&CK** section. It names relevant Enterprise
techniques, links to MITRE, and explains whether the control reduces the likelihood of an
attack, helps detect or contain it, supports recovery, or enables another safeguard.
You can search the workspace by technique ID (for example, `T1110.004`), technique name,
or mitigation ID. Search by name requires the ATT&CK source to be loaded.

These control mappings are WACC's assessments. Where a MITRE mitigation is cited, its
relationship to the technique is checked against the downloaded ATT&CK data. Controls
without a defensible direct mapping, such as external incident notification, explain
that limit. The mapping uses Enterprise ATT&CK 19.2; it does not claim Mobile or ICS
technique coverage. ATT&CK is a trademark of The MITRE Corporation. See
[MITRE ATT&CK](https://attack.mitre.org/) for the publisher's technique descriptions.

The source browser preserves provenance, framework identity and hierarchy so readers can
return to the relevant publisher record. Source documents retain their own licences and
attribution. See [sources/README.md](sources/README.md) for automatic downloads, manual
acquisition and edition checks.

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
