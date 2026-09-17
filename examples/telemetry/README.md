# Example security logs

These fictional Sentinel and Defender events support the Department of Silly Walks
annual assessments. They include application control, sign-ins, endpoint protection,
software inventory, vulnerabilities, incidents and other security evidence.

## Generate the files

Run from the repository root:

```powershell
python tools/build_telemetry_examples.py
```

The script writes into this folder:

```text
examples/telemetry/
  2023/  manifest.json and 12 event files
  2024/  manifest.json and 12 event files
  2025/  manifest.json and 12 event files
```

Each manifest records the assessment scope, evidence period and file hashes. Most
event files use JSON lines; the 2025 sign-in sample uses CSV to demonstrate that format.
The script locates the output folder from its own file location. Running it again
overwrites the generated examples. It runs offline and needs no tenant connection.

## Use the examples

1. Start the application with `python -m wacc serve`.
2. Open **Assessments** and select **Import the three examples**.
3. Select a year and open **Validate against security logs**.
4. Select **Validate this year's example logs**.
5. Review the findings, record review decisions and download the report.

Repeat for the other years to compare the evidence alongside the annual maturity
trend. See the [spreadsheet guide](../assessments/README.md) for assessment imports.

Generated files remain in this folder. Imported validation runs, evidence and review
history are stored separately under `data/local/assessments/validation/` by default.

## Use your own logs

Follow the [collection, import and review guide](../../docs/telemetry-validation.md)
for supported formats, scope manifests, local uploads and Azure Data Lake Storage
Gen2 imports. [Export queries](export-sentinel.kql) provide starting points for
collecting the supported Sentinel tables.
