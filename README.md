# WA Control Crosswalk

WA Control Crosswalk (WACC) brings cybersecurity controls, assessment methods and
source requirements together. Its new offline desktop pilot reviews how selected
policy documents address those requirements, with source passages and separate
reviewer decisions.

Use it to find controls by topic, review their business risks, follow related
requirements and choose which sources to include. Each control provides GRC and
technical assessment guidance, with documents to inspect, practical tests and
expected results.

The existing control library remains available in the local web interface.
The scripts acquire and prepare source documents, analyse topic coverage and
check the integrity of the data and application.
Assessment commands are provided for users to run in their own environments.

## Run locally

Requires Python 3.9 or later. From the repository folder:

```powershell
python -m wacc sources
python -m wacc serve
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/).
See [setup and troubleshooting](HOW-TO-RUN.md) for more detail.

## Offline policy review pilot

```powershell
python -m pip install -r requirements-policy.txt
python -m wacc open
```

The desktop and CLI share one deterministic engine. They work offline with local
TXT, Markdown, DOCX and text PDF files, save `.wacc` assessments, and export reports.
No AI service or model runs during analysis. Coverage describes documented policy,
not implementation or compliance.

The current pilot automates one draft rule family; other requirements remain
available for manual review. Human rule approval and enterprise deployment testing
are still required. Start with the [plain-English desktop guide](docs/policy-review/README.md).
Command-line and deployment details are linked there.

## Repository guide

| Folder | What it contains |
|---|---|
| [wacc/](wacc/) | Application code, source loaders, search and web interface. |
| [data/](data/README.md) | Controls, assessment methods, source mappings and coverage reports. |
| [sources/](sources/README.md) | Source acquisition records and instructions for adding a framework. |
| [tools/](tools/README.md) | Data preparation, source reviews and validation scripts. |
| [tests/](tests/README.md) | Automated checks and instructions for running them. |
| [docs/](docs/README.md) | Detailed workflows, design notes and review reports. |
