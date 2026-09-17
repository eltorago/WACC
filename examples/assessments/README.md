# Annual self-assessments

Open **Assessments** from the control workspace, or visit
[http://127.0.0.1:8765/assessments](http://127.0.0.1:8765/assessments).
The page compares annual assessments against the **WA Cyber Security Policy 2024**.
It shows a maturity trend, results for its six policy areas, and the evidence and actions
behind each requirement rating. Requirement links open the policy in the corpus;
related controls open their GRC and technical assessment methods.

To try it, select **Import the three examples**. The fictional Department of Silly Walks
improves from **1.00 / 4 in 2023** to **2.44 / 4 in 2024** and **3.70 / 4 in 2025**.
The 2023 workbook is a retrospective assessment against the 2024 criteria. All three
use the same departmental scope and 86 requirement rows.

To import your own assessment:

1. Download **Blank assessment template** from the page. The XLSX files are also in
   [this folder](.).
2. On **Overview**, enter the department, assessment year and date, assessor and scope.
   Mark an assessment of a year before 2024 as retrospective. Record the accountable
   authority, approval date, Annual Implementation Report (AIR) status and reference,
   and exemption references in **Approval and reporting**. These fields are unscored.
3. On **Assessment**, complete the amber fields: rating, evidence reference or observation,
   owner, next action and due date. Keep the requirement IDs, prompts and column headings.
4. Choose **0 Not started**, **1 Planned**, **2 Partly implemented**, **3 Implemented** or
   **4 Tested and reviewed**. Ratings 3 and 4 require evidence. Use **Not assessed** for
   outstanding work, or **N/A** with an exclusion reason. Keep every requirement row.
   Include the relevant DGov exemption approval reference where applicable.
5. Save as `.xlsx`. Select one or more annual files on the Assessments page and click
   **Import selected files**. Each file may be up to 5 MB, with 20 MB and ten files per batch.
6. Select the department and year. Click a policy-area score or use the area filter to
   review its requirements. Selecting a year or area refreshes the results immediately.
7. To correct an imported department/year, edit the workbook and import it with
   **Replace existing years** selected. Importing the identical file again is harmless.

**How scores work:** this WACC scale tracks implementation and review progress; it is
not an official WA or Essential Eight maturity level. Scores are the equal-weight mean
of applicable requirement ratings. A missing rating leaves the score unavailable.
N/A rows are excluded. The trend uses the same applicable requirements across all years;
the policy-area table uses each year's applicable requirements and shows its exclusions.
WACC recalculates results from the ratings rather than trusting spreadsheet formula caches.
The policy prompts are authored summaries with stable references to the locally acquired
[2024 policy](https://www.wa.gov.au/system/files/2024-12/wacybersecuritypolicy.pdf).
Approval and reporting fields reflect page 22. For formal AIR submissions, use the
format prescribed by DGov.

**Where imports go:** assessed values and the workbook hash are stored in
`data/local/assessments/records.json`, which is excluded from Git and release packages.
Imports survive restarts. Keep the original XLSX files and back up this JSON file.
Set `WACC_ASSESSMENTS` before starting the server to use another private storage directory.
Only the fictional example files and blank template are included in the repository.
The local server has no user accounts or department-level access restrictions; protect
access to it and its storage before using real assessments in a shared deployment.

## Files and maintenance

- [Blank template](wa-csp-2024-template.xlsx).
- [2023 example](department-of-silly-walks-2023.xlsx).
- [2024 example](department-of-silly-walks-2024.xlsx).
- [2025 example](department-of-silly-walks-2025.xlsx).

See [assessment design and rebuilding](../../docs/department-assessments.md) for
workbook generation, import validation and storage details. To compare an assessment
with security events, use the [log examples](../telemetry/README.md).
