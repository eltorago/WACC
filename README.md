# WA Control Crosswalk

WA Control Crosswalk (WACC) is a local web application for exploring cybersecurity
controls across Australian and international frameworks, with a specific focus on Western Australian entities covered by the WA Cyber Security Policy (WA CSP).

It is entirely written by AI tools along with some manual changes to descriptions.

It brings related requirements together without hiding the original source text
or treating a crosswalk as proof of compliance.

The application currently includes a workspace of **84 practical controls across 30
topics**. Each control has:

- a plain-English control statement and business risk;
- guidance on what to examine and who to interview;
- a four-step testing method and expected result;
- reviewed links to relevant publisher requirements; and
- links to other controls that address the same problem.

The wider source browser contains **more than 5,300 records from 18 frameworks, WA CSP included**. You can search by
subject or identifier, inspect the source wording and published assessment material, move
between linked controls, limit results to selected frameworks and export mappings to CSV.

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

## How the repository is organised

| Path | Purpose |
|---|---|
| `wacc/` | Loads the corpus, finds controls, builds relationships and serves the web and command-line interfaces. |
| `data/library/` | The 84 locally written workspace controls, grouped into one JSON file per topic. |
| `data/corpus/` | Curated extracts used when a publisher does not provide a suitable machine-readable source. |
| `data/validation/` | Search expectations and the topic-frequency report used to check coverage and ranking. |
| `sources/acquisition.json` | Publisher download locations and instructions for sources that need manual acquisition. |
| `sources/permissions.json` | File hashes, source links, permissions and attribution evidence for reviewed documents. |
| `sources/files/` | Ignored local cache populated by `python -m wacc sources`; publisher files are not distributed with WACC. |
| `tools/` | Import and verification utilities used to rebuild or check parts of the corpus. |
| `tests/` | Regression checks for source permissions, loading, search, relationships, assessments and rendering. |

## How to read the results

The workspace controls and their assessment methods are locally authored. Their source
links describe reviewed overlap with publisher requirements. A linked requirement may
address all of a control, only part of it, or provide related context. Meeting a workspace
control therefore does not automatically meet every linked framework requirement.

The source browser preserves provenance, framework identity and hierarchy so readers can
return to the relevant publisher record. Source documents retain their own licences and
attribution. See [sources/README.md](sources/README.md) for automatic downloads, manual
acquisition and edition checks.

## Check a change

Run the complete regression suite from the repository root:

```powershell
python tests\run_all.py
```

For changes to the Control workspace, the focused check is:

```powershell
python -m unittest tests.test_control_workspace tests.test_terms
```
