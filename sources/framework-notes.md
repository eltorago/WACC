# Framework relationships and editions

Source-set notes moved from the main README on 17 September 2026.

The **Essential Eight is a subset of the 37 ACSC mitigation strategies**. WACC groups
them as one framework family. Mixed search results, workspace references and frequency
reports prefer Essential Eight maturity detail over the matching broad strategy row.
Both source editions remain directly accessible: February 2017 strategies and November
2023 maturity requirements. Raw record counts include both editions; they are not a
count of distinct controls. [ACSC describes the relationship here](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight).

**ASD Cyber Security Principles** is a separate framework scope option. It contains
the 49 September 2026 principles across Govern, Identify, Protect, Detect, Respond
and Recover, with 101 reviewed links to workspace controls. Search **ASD principles**
for the whole source set, or a source identifier such as `asd-principles:PRO-12`.
The principles load from ASD's official ISM OSCAL download and are counted once;
the ISM scope contains the remaining 1,143 numbered security controls. Existing
`ism:gov-1`-style links still resolve. Both source sets belong to the ISM family.
The [ASD principles page](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/ism/cyber-security-principles)
is also acquired automatically for source review. Reproduce the comparison with
`python tools/review_asd_principles.py` after acquiring sources.

See the [WA PRIS framework review](../docs/wa-pris-framework.md) for its coverage, commencement and source checks.
