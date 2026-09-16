# Framework coverage review

Reviewed 16 September 2026 against the SCF 2026.2 workbook. SCF is used as an inventory of referenced frameworks; its control prose is not reproduced in this report. The workbook stays local.

The workbook contains 1,534 SCF controls, 252 external mapping columns and 254 focal-document metadata rows. Columns include editions, profiles and overlays; these are not counts of distinct frameworks.

Counts below mean SCF controls with a non-empty mapping cell. They are not counts of target controls, independent mentions, legal applicability or evidence of compliance.

## Cloud and Microsoft 365 priorities

This pass adds SCF as a locally imported meta-framework, ASD Essential Eight, Microsoft cloud security benchmark v1 and seven CISA SCuBA Microsoft 365 baselines. MCSB and SCuBA were selected from Microsoft, ACSC and WA OAG context even though they are absent from SCF’s inventory. MCSB v2 is a preview; this import explicitly uses the complete v1 workbook.

| Framework | Status | SCF controls mapped | Why it matters / acquisition |
|---|---|---:|---|
| [CSA CCM 4.1.0](https://cloudsecurityalliance.org/group/cloud-controls-matrix/#_overview) | Next | 291 | Cloud customer/provider responsibilities and assurance. Obtain the official CCM under its publisher terms before importing requirements. |
| [ISO 27017:2015](https://www.iso.org/standard/43757.html) | Licensed source needed | 224 | Cloud security responsibilities. Acquire licensed ISO text; SCF references do not license the standard or replace its requirements. |
| [ISO 27018:2025](https://www.iso.org/standard/27018) | Licensed source needed | 322 | Personal data in public cloud. Acquire the current licensed standard from ISO or an authorised distributor. |
| [AICPA TSC 2017:2022](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022) | Next | 412 | Provider assurance: obtain the criteria and each supplier’s assurance report; a SOC 2 report is entity-specific, not a generic certificate. |
| [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final) | Next | 93 | Cloud and hybrid zero-trust architecture; complements the existing CISA maturity model. |
| [ISO 27001:2022](https://www.iso.org/standard/27001) | Licensed source needed | 51 | Management-system assurance. Obtain licensed publisher text; do not infer certification from control overlap. |
| [ISO 27002:2022](https://www.iso.org/standard/75652.html) | Licensed source needed | 316 | General controls guidance. Obtain licensed publisher text before a full requirements import. |
| [ASD Essential Eight](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight/essential-eight-maturity-model-and-ism-mapping) | Added; edition review | 37 | WACC imports the current publisher page labelled November 2023. SCF labels its column 2024; no automatic transfer of these mappings. |
| [ASD ISM](https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/ism) | Already present; different edition | 389 | WACC uses September 2026; SCF uses March 2026. Compare changes before accepting SCF mappings. |
| [CIS Controls](https://www.cisecurity.org/controls/v8-1) | Already present; different edition | 234 | WACC uses v8; SCF uses v8.1. The Microsoft workbook’s v8 references are kept separate. |
| [NIST CSF 2.0](https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf) | Already present | 250 | Same named edition. SCF cross-references remain publisher assertions, not compliance determinations. |
| [NIST SP 800-53 R5](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final) | Already present; minor revision unspecified | 777 | SCF names R5 without WACC’s 5.2.0 minor revision. No automatic SCF-to-800-53 links are imported. |

## Scope and provenance

WA legislation, policy and OAG guidance already in WACC remain relevant even when SCF does not name them. CISA federal baselines are informational for WA organisations. US-specific data types, reporting recipients and mandatory language must be assessed for local applicability.

Imported SCF links are limited to resolvable NIST CSF 2.0 references. Generic NIST R5 and older ATT&CK, ISM and CIS columns are not silently translated to the loaded editions. Workspace technical checks are independently authored from the separately cited ACSC, Microsoft and CISA guidance.

The complete mapping-column inventory and non-empty counts are in `data/framework-review.json`. To reproduce: `python tools/framework_gap_report.py`. Source: https://github.com/securecontrolsframework/securecontrolsframework
