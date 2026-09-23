# Review your policies with WACC

WACC can compare your policy documents with framework requirements, show the
passages it finds, and save your review decisions. Everything stays on your
computer. Reviewing documents needs no internet connection or AI service.
Downloading framework updates needs internet access.

Choose **WA CSP**, **ASD ISM**, **AESCSF**, or any combination. Reports show
coverage separately for each framework. This is an early desktop version: annual
staff awareness training under WA CSP has a draft automated check. Other
requirements currently need manual review.
The results describe what your documents say; they do not test your systems.

## Open the desktop

From the repository folder, using Python 3.13 on Windows:

```powershell
python -m pip install -r requirements-policy.txt
python -m wacc open
```

Install the dependencies once. After that, just run the second command.
Before creating an assessment, open **Framework updates**, select the frameworks
you need, and choose **Download updates**. WACC obtains and prepares the publisher
files. If a download is blocked, follow the displayed instructions, select only
that framework, and use **Import framework file** to add your downloaded copy.
Existing local source collections also work.

If you have a built application folder, keep the whole folder together and follow
the [launch instructions](../deployment/POLICY-PILOT.md#build-and-launch).
The existing control workspace still opens with `python -m wacc serve`.

## 1. Choose the documents

Select **New assessment** and fill in:

| Field | What to enter |
|---|---|
| **Name** | A useful name, such as “IT policy review — September”. |
| **Organisation** | The organisation or team being reviewed. |
| **Scope** | Exactly what the review covers, such as “Approved IT policies for head office”. |
| **Approval** | Whether the selected documents are approved, draft, superseded or unknown. This setting applies to every document selected for this run. |
| **Retention** | Choose **evidence** to keep matching passages, or **extracted** to keep all extracted text for manual review. |

Select one or more **Frameworks to assess**. Then select **Add documents** and
**Analyse and save**. Choose where to save the
`.wacc` assessment file. You can use Word documents (`.docx`), text PDFs, plain text
and Markdown. Scanned PDFs need text recognition outside WACC first.

For a quick demonstration, add [positive.md](../../examples/policy-review/positive.md),
select only **WA CSP**, set **Approval** to **approved**, and use “Training policy demonstration” as the
scope. This is fictional test text. The expected result is one full evidence
candidate and 85 requirements not assessed automatically.

## 2. Read the results

**Overview** shows how many documents were read, how much was assessed and how
many requirements you have reviewed. The framework table separates WA CSP, ISM
and AESCSF totals. Any document-reading problems appear here.

Open **Requirements**, search for a reference or subject, and select a requirement.
The right-hand panel shows its wording and the individual points to check.
Select an **Evidence passage** to read the matching text, with the relevant words
highlighted and its source location recorded.

| Result shown in WACC | Meaning |
|---|---|
| **FullCandidate** | Text was found for every point the automated check covers. Review it before accepting it. |
| **PartialCandidate** | Text was found for some points; others are missing. |
| **NoEvidenceFound** | The check found no qualifying text in the selected documents. |
| **Ambiguous** | The wording or document status needs closer review. |
| **NotAssessed** | There is no automated check, or a problem prevented assessment. |

Use **Potential gaps** to find missing evidence and **Documents** to inspect
what was read. A result of “100%” for the automatically assessed subset can mean
just one of the 86 requirements; check the assessment completeness alongside it.

## 3. Record your decision

Select **Review finding / confirm / reject**.

1. Enter your name, choose a finding, and explain your reason.
2. Select the individual points you have confirmed.
3. Select the evidence you accept. Leave rejected evidence unselected.
4. Use **Link another retained passage** if you found better supporting text.
5. Select **Save reviewer decision**.

Hold **Ctrl** to select more than one point or passage. A **Covered** decision
needs evidence for every required point. Choose **extracted** retention when
you want to review passages beyond those found automatically.

Your decision is saved separately from the automatic result. Both remain visible.

## 4. Return later or share a report

Use **Open** to return to a saved `.wacc` file. WACC restores its saved results
without running the analysis again.

- **New analysis run** lets you choose updated documents and keeps earlier runs
  in **History**. Previous decisions need another review.
- **Save snapshot** saves a separate copy of the assessment.
- **Finalise snapshot** prevents further review changes to the current run in
  WACC. Start a new analysis run when you need to revise it.
- **Export report** lets you select which assessed frameworks to include. Clear
  **Include evidence excerpts and review notes** for a summary-only report, then
  choose **Save report**. Formats are HTML, CSV, Markdown and JSON.

HTML reports open in a browser without a web server. The assessment file can
contain policy text and review notes, so keep it in an appropriate local folder.
Original documents stay where they are; WACC does not embed them in the assessment.

## Keep the frameworks current

Return to **Framework updates** and choose **Download updates** when you want to
check for new publisher files. WACC shows whether each framework was updated,
unchanged or could not be downloaded. Failed updates leave the previous copy in
place. Updates affect new analysis runs; saved assessments keep their original
framework wording, versions and findings.

## More detail

- [Command-line use, limits and source preparation](../policy-review.md)
- [Build and deployment instructions](../deployment/POLICY-PILOT.md)
- [Implementation status and checks](../POLICY-IMPLEMENTATION.md)

<!-- Actual screenshots are pending: Windows capture failed on the development
host. Add Overview, requirement 3.2a with evidence, and Review finding captures
from the fictional example above. Do not substitute mock-ups for screenshots. -->
