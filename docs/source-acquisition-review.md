# Source acquisition review

Reviewed 16 September 2026.

WACC has 74 source documents: 64 configured automatic routes and 10 manual acquisitions. A live forced-download check verified 59 automatic downloads. Four routes were blocked by publishers; one served a different document edition or file. Existing matching local files were retained on every failure.

## Remaining automatic-download exceptions

| Document | Result | Next step |
|---|---|---|
| aescsf-framework-core.xlsx | Publisher returned HTTP 403 | Use the publisher in a normal browser and import the reviewed file. |
| cisa-vulnerability-review-fy-2024-2025-508.pdf | Publisher returned HTTP 403 | Use the publisher in a normal browser and import the reviewed file. |
| Joint-Guidance-Identifying-and-Mitigating-LOTL508.pdf | Publisher returned HTTP 403 | Use the publisher in a normal browser and import the reviewed file. |
| NCSC-Secure-Connectivity-for-Operational-Technology.pdf | Reviewed hash did not match | Review the current NCSC document before updating the corpus and expected hash. |
| zero_trust_maturity_model_v2_508.pdf | Publisher returned HTTP 403 | Use the publisher in a normal browser and import the reviewed file. |

## Manual sources

Nine CIS documents still need publisher sign-in or download steps. The NIST CSF OLIR workbook needs an interactive export. The Sources page links to their publishers and gives acquisition instructions. The local cache already contains five of these ten files; that does not imply they are automatically downloadable.

## Stable verification

NIST digital-identity HTML is downloaded from pinned official repository commit `4f2487bb81adecdc84ccaac6920bf0b500b379ae`. All four files were compared with the previous reviewed copies: only the website-injected analytics script is absent; document content is identical.

OAG report HTML contains rotating nonces and form values. For the 13 reviewed reports, WACC fingerprints the complete report header and body, including title, date, text, links and image references. Changed, missing, duplicated or truncated report sections fail verification. Only site material outside those sections is excluded. Original HTML is saved unchanged, never executed or served, and remains excluded from distribution.

All other documents require the reviewed whole-file SHA-256. Acquisition never accepts a new edition solely because it is the latest publisher download.

## Workflow

Use Sources in the app to download and reload, `python -m wacc sources --status` for an offline inventory, or `python -m wacc sources --import-from "C:\path\to\downloads"` to recognise manually downloaded files. Downloads have bounded discovery and timeouts, retry transient errors, report progress as each file completes, and preserve existing files when verification fails.

## ACSC mitigation strategies addition

The subsequent assessment review added two automatic source routes: the official February 2017 strategy table and its companion mitigation details. Both downloads succeeded and their original bytes were pinned in the permissions manifest. The current catalogue therefore has 76 documents: 66 automatic routes (61 verified across the two reviews) and 10 manual acquisitions. Publisher files remain in the ignored local cache.
