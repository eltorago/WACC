# WA Control Crosswalk

WACC brings cybersecurity frameworks, controls and assessment guidance together.
It also compares policy documents with selected frameworks, showing related
passages and requirements that are not mentioned.

Choose several documents or a ZIP archive. Results link back to the original
text and can be exported as a report for the frameworks you select. Comparisons
run locally, without an AI service. Framework updates download publisher files
when requested.

## Run the desktop

Use Python 3.13 on Windows. From the repository folder:

```powershell
python -m pip install -r requirements-policy.txt
python -m wacc open
```

Start with the [plain-English guide](docs/policy-review/README.md) for adding
frameworks, importing documents and reading the results.

The control library is also available through `python -m wacc serve` at
[http://127.0.0.1:8765/](http://127.0.0.1:8765/).
See [library setup](HOW-TO-RUN.md) for source preparation and troubleshooting.

## Repository guide

| Folder | What it contains |
|---|---|
| [wacc/](wacc/) | Application code, document comparison, loaders, search and interfaces. |
| [data/](data/README.md) | Controls, assessment methods and source mappings. |
| [sources/](sources/README.md) | Source acquisition records and instructions for adding frameworks. |
| [tools/](tools/README.md) | Scripts to prepare sources, build the app and measure performance. |
| [tests/](tests/README.md) | Automated checks and instructions for running them. |
| [docs/](docs/README.md) | Detailed workflows, design notes and deployment instructions. |

The scripts acquire and prepare source documents, check data quality, test the
application and build the Windows package. Development and build tools are
listed separately in `requirements-policy-dev.txt`.
