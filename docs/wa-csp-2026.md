# WA Cyber Security Policy 2026

WACC now uses the [2026 WA Government Cyber Security Policy](https://www.wa.gov.au/government/publications/wa-government-cyber-security-policy).
It replaces the 2024 edition in the WA CSP framework filter.

## Update an existing installation

From the repository folder, run:

```powershell
python -m pip install pdfplumber
python -m wacc sources --only "wa-cyber-security-policy.pdf" --force
python tools/extract_wa_csp.py
python -m wacc serve
```

Stop the previous WACC server before restarting it. `--force` replaces an older
local policy PDF; it still requires the downloaded file to match the reviewed
2026 edition. If you need the 2024 PDF for historical work, copy it elsewhere first.
Downloads respect `WACC_SOURCES` when that environment variable is set.

On startup or corpus reload, WACC also rebuilds a missing or older WA CSP extract
from the reviewed local PDF. If the PDF is missing or belongs to another edition,
the framework is listed as unavailable with instructions. The tool does not apply
2026 mappings to the 2024 text.

## What changed

The import contains 58 numbered headings and 218 clause records across the six
policy functions. Headings and lettered clauses produce 262 searchable records;
that is a record count, not a count of distinct security controls.

Nested requirements retain their numbering, introductory text and source page.
Existing workspace references were checked and corrected where clauses moved.
There are also 93 new links from workspace controls to the expanded policy,
including MFA, application control, privileged access, backups, logging, AI,
operational technology and post-quantum planning. These are WACC's reviewed
mappings, labelled **Locally reviewed mapping**.

Notable dates and timeframes are preserved in the source clauses:

- Domain 3 implementation: December 2028.
- Documented post-quantum transition approach: December 2027.
- Incident notification: six hours for DGov and twelve hours for ACSC.

The policy uses different starting events for the ACSC deadline: section 5.1 says
**detection**, while section 5.2c says **confirmation**. WACC retains both texts.
The incident-notification assessment asks for detection, suspicion and confirmation
timestamps so the reviewer can check each clause.

Search for `wa-csp:3.1.5` to see application-control requirements, `wa-csp:3.14`
for AI security, or `wa-csp:5.1` for incident reporting. Existing links whose
numbers were reused by the publisher now refer to the 2026 clause; WACC does not
present old and new editions under the same identifier.

## Source and checks

Reviewed PDF: [2026 policy, version 2](https://www.wa.gov.au/system/files/2026-10/2026.wa_.cyber_.security.policy.v2.pdf),
44 pages, downloaded 12 October 2026. SHA-256:

```text
4be54cb6ead0f614ff72f90b65690e5b3ad7fcf891c1c31627922a9d286d1ac9
```

Credit: State of Western Australia, Department of the Premier and Cabinet.
The PDF and extracted policy text remain local and are excluded from Git and
release packages. The source record retains the [WA terms of use](https://www.wa.gov.au/terms-of-use).

Run `python tests/test_wa_policy.py` for extraction, numbering, source verification,
cache migration and workspace-link checks. The source integration checks need the
reviewed PDF. Run `python tests/run_all.py` for the full regression suite.
