# WA Control Crosswalk

WA Control Crosswalk (WACC) brings cybersecurity controls, assessment methods and
source requirements into one local web application.

Use it to find controls by topic, review their business risks, follow related
requirements and choose which sources to include. Each control provides GRC and
technical assessment guidance, with documents to inspect, practical tests and
expected results. The application also compares annual spreadsheet assessments
and checks supporting security logs.

The scripts acquire and prepare source documents, generate fictional examples,
analyse topic coverage and check the integrity of the data and application.
Assessment commands are provided for users to run in their own environments.

## Run locally

Requires Python 3.9 or later. From the repository folder:

```powershell
python -m wacc sources
python -m wacc serve
```

Open [http://127.0.0.1:8765/](http://127.0.0.1:8765/).
See [setup and troubleshooting](HOW-TO-RUN.md) for more detail.

## Repository guide

| Folder | What it contains |
|---|---|
| [wacc/](wacc/) | Application code, source loaders, search and web interface. |
| [data/](data/README.md) | Controls, assessment methods, source mappings and coverage reports. |
| [sources/](sources/README.md) | Source acquisition records and instructions for adding a framework. |
| [tools/](tools/README.md) | Data preparation, example generation and validation scripts. |
| [examples/](examples/README.md) | Sample spreadsheets and security logs, with their own usage guides. |
| [tests/](tests/README.md) | Automated checks and instructions for running them. |
| [docs/](docs/README.md) | Detailed workflows, design notes and review reports. |
