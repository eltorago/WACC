# Compare policies with frameworks

WACC shows where your policy documents mention subjects in the **WA CSP**,
**ASD ISM** and **AESCSF**, and which requirements have no matching passage.
Choose one framework or any combination. Results stay separate for each framework.

## Open WACC

From the repository folder, using Python 3.13 on Windows:

```powershell
python -m pip install -r requirements-policy.txt
python -m wacc open
```

Install dependencies once. On later visits, run only the second command.
Built application folders can open without installing Python; see
[build and launch](../deployment/POLICY-PILOT.md#build-and-launch).

Before the first comparison, open **Framework updates**, select the frameworks
you need and choose **Download updates**. If a publisher blocks a download,
download its file yourself and use **Import framework file** with that framework
selected. Existing prepared local source collections also work.

## Add documents

1. Select **New comparison**.
2. Give it a name, optionally enter your organisation, and describe the scope.
3. Select the frameworks to compare against.
4. Choose **Add files or ZIP archives**. Select several files at once with Ctrl
   or Shift, add files in batches, or choose one or more ZIPs.
5. Select **Compare and save**, then choose a name for the `.wacc` file.

Supported documents are Word (`.docx`), text PDFs, plain text and Markdown.
Folders inside ZIPs are supported. WACC reads archive members without unpacking
files onto your computer. Unsupported files are listed as skipped; nested ZIPs
are skipped too. Password-protected and unsafe archives are rejected.

You can select up to 250 documents in total, including files inside archives.
Each input is limited to 16 MiB; ZIP contents may expand to 32 MiB. Scanned PDFs
need text recognition before importing. Duplicate documents are counted once.

For a demonstration, select both files in
[the example policy folder](../../examples/framework-alignment/). They are
fictional documents with access, training, backup and incident-response content.
You can also put those files in a ZIP and import that archive.

## Read the results

**Overview** shows totals for each selected framework. **Requirements** lets you
search or filter the results. Select a requirement to see the framework wording
alongside matching policy passages. Relevant words are highlighted, with the
file name and page, paragraph or table location.

| Result | Meaning |
|---|---|
| **Mentioned** | A passage shares clear wording about the requirement. |
| **Related wording** | A possible topic match, a named reference or qualified wording. |
| **Not mentioned** | No matching passage was found in the supplied documents. |
| **Unable to check** | Some document text could not be read or was not retained. |

**Not mentioned** collects unmatched requirements so you can identify subjects
to add to your policies. It keeps unreadable-document cases labelled separately.
**Documents** shows what was read, including each file inside a ZIP.

Matching uses local wording, spelling variants and common technical acronyms.
It finds topics and passages; it does not decide whether the policy satisfies
every part of a requirement. Very different wording can need a manual search.
Up to five of the clearest passages are shown per requirement, with the total
match count. Framework mappings do not transfer matches between requirements.

## Save and share

Use **Open** to return to a `.wacc` file. **Compare new documents** creates a new
run while keeping earlier results in **History**. **Save a copy** makes a separate
copy of the saved comparison.

**Export report** lets you choose frameworks and whether to include matching
policy passages. Available formats are HTML, CSV, Markdown and JSON. HTML reports
open in a browser without a server. Reports group requirements into the same
four results shown in the app.

Comparisons retain extracted text and their framework snapshots. Original files
stay where they are. Keep the `.wacc` file and reports in an appropriate local folder.
Older assessment files remain readable; if they retained only selected passages,
start a new comparison with the original documents to search the complete text.

## Update frameworks

Use **Framework updates → Download updates** to check for newer publisher copies.
Failed updates leave the previous copy in place. New comparisons use the updated
frameworks; saved comparisons retain their original wording and results.

## More detail

- [Commands, matching and file limits](../policy-review.md)
- [Build and deployment](../deployment/POLICY-PILOT.md)
- [Optimisation and validation notes](../OPTIMISATION.md)
