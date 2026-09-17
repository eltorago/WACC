# WA Privacy and Responsible Information Sharing Act

WACC imports the **Privacy and Responsible Information Sharing Act 2024 (WA)** from
the [WA Legislation website](https://www.legislation.wa.gov.au/legislation/statutes.nsf/law_a147470.html).
The reviewed edition is **00-g0-01, current from 1 July 2026**, downloaded on
17 September 2026.

Select **WA PRIS Act** under Framework scope. Search the source browser for `PRIS`,
`PRIS IPP 4.1`, `PRIS RSP 3.1` or `wa-pris:s 79`. Workspace references open the full
provision and its related controls. The source browser retains the Act's sections,
definitions, exceptions and transitional rules.

## Coverage

- 214 sections from the current consolidation.
- All 11 Information Privacy Principles in Schedule 1, with numbered subclauses searchable individually.
- All five responsible-sharing principles in Schedule 2; RSP 3.1 and 3.2 remain distinct from the privacy principles.
- 333 records: 266 provisions with text and 67 structural headings.
- 73 locally reviewed mappings to 16 existing workspace controls covering privacy,
  data protection, access, governance, risk, suppliers, media disposal and incident response.

The mappings name practical evidence to inspect: collection notices, written processing
purposes, privacy policies, access and correction case files, retention schedules,
privacy impact assessments, sharing assessments and agreements, and officer designations.
Source assessments distinguish privacy access requests from system-account access,
and use case files, privacy impact assessments and collection records as evidence.
Automated-decision obligations have related links to the existing privacy controls;
those controls do not yet provide a complete automated-decision assessment.

## Application and commencement

Entity definitions and exclusions are in sections 6–8, 14 and 17–27. Section 129
allows State services contracts to apply the privacy obligations to a provider;
the importer does not assume that every supplier is an IPP entity.

Section 223 limits IPPs 1, 7, 8 and 10 to information collected on or after
1 July 2026. Other IPPs also apply to existing information. These principles link
directly to the transitional provision. IPP 6 results link to section 27 so users
can check the applicable access and correction route, including FOI exclusions.
Section 79 links to section 227 for existing activities and significant changes.

The consolidation excludes the following uncommenced provisions:

- Part 2 Division 6: sections 57–75, the notifiable information breach scheme.
- Part 2 Division 10 Subdivision 4: sections 118–121.
- Sections 134–136 concerning contracted service providers and breach matters.
- Part 3 Division 6: sections 191–195 concerning shared information breaches.

The [Office of the Information Commissioner](https://www.wa.gov.au/organisation/office-of-the-information-commissioner/privacy-western-australia)
records the Government's announced **1 January 2027** start for the notifiable
information breach scheme. The current compilation table still records the excluded
provisions as awaiting proclamation. Sections 151, 170 and 225 retain their published
references to those provisions, with a short status note in WACC.

The existing annual department assessments continue to assess the WA Cyber Security
Policy 2024. PRIS is an additional source framework, not a change to those assessment
criteria or historical ratings.

## Acquire and verify

```powershell
python -m wacc sources --only wa-pris-act-2026-07.docx
python tools/review_wa_pris.py
python tests/test_wa_pris.py
```

The first command downloads the reviewed Word document into the ignored local source
cache. The review command reads the official HTML rendition and checks every imported
provision's letters and numbers in order, ignoring punctuation and layout differences.
All 266 provisions matched on 17 September 2026. The review records source hashes and
per-provision hashes in `data/validation/wa-pris-review.json`.

The importer rejects a different source hash until its edition has been reviewed.
To update it, check the latest consolidation and commencement table, update the
source catalogue, registry and loader's reviewed hash, then review section boundaries,
mappings and commencement notes. Run the comparison and regression suite, followed by
`python tools/revalidate_corpus.py` and `python tools/analyse_topics.py`.
Use the Sources page to reload the application, or restart the local server.

## Attribution

© State of Western Australia 2026. CC BY 4.0. Based on content from the Western
Australian Legislation website at 17 September 2026. For the latest information on
Western Australian legislation, visit [WA Legislation](https://www.legislation.wa.gov.au/).
WACC structures the provisions and adds local mappings. The original Word document
stays in the local cache; it is not hosted in this repository. The
[publisher's licence](https://www.legislation.wa.gov.au/legislation/statutes.nsf/copyright.html)
excludes the crest and other specified material.
