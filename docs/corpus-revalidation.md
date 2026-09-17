# Corpus revalidation and additional control candidates

Review date: 2026-09-17

7,728 source records across 23 framework families (25 source sets); 84 practical controls, 58 technical checks and 13 dated OAG reports.

## Integrity checks

Checked local publisher hashes, acquisition catalogue consistency, corpus structure, every corpus link, every workspace source reference and technical-check coverage for all practical controls.

Blocking integrity problems: 0.

## Recommended additional controls

These are candidates for distinct practical controls or topics, not claims that the subjects are entirely absent. Related technical checks already exist in this change. Priority reflects distinct scope and WA/cloud relevance, not a frequency-derived risk score. No new practical control has been created automatically from a text match.

| Candidate | Priority | Current partial coverage | Why add it |
|---|---|---|---|
| Email authentication and message protection | High | UH-01, UH-02, DP-03 | Create a dedicated workspace topic and control covering domain authentication, impersonation, attachment/link protection and mail-flow exceptions. Technical checks exist, but they currently sit beneath broad application-hardening controls. |
| Application identities and consent | High | IA-02, IA-03, SD-01 | Add a dedicated control for non-human identity ownership, permissions, consent, credentials and retirement. Existing identity controls cover parts of the lifecycle; users need a direct route to these cloud-specific checks. |
| External collaboration and guest access | High | IA-01, IA-02, DP-03, SC-03 | Add a control joining guest sponsorship, cross-tenant trust, sharing links and collaboration expiry. Coverage is currently divided between access, data protection and supplier controls. |
| Low-code applications and public analytics | High | SD-01, DP-03, PI-02 | Create a control for environment ownership, connector boundaries and public publication. This is a distinct business-managed application path, with technical assessment coverage now available. |
| Business application authorisation and data integrity | High | IA-02, SD-03, PI-02 | Add a control for transaction limits, conflicting duties, record-level access and verified data changes. The State Government 2025 and Assist audits provide specific WA examples; configuration and software-testing controls alone do not express this business outcome. |
| Cloud tenant and subscription governance | Medium | AM-01, AM-02, GV-01, SC-02 | Consider a dedicated control joining tenant ownership, approved subscriptions/services, shared responsibility and drift monitoring. Existing controls and the new baseline assessment provide substantial partial coverage. |
| AI agent and assistant access | Medium | IA-02, DP-03, SD-02 | Review a separate control for agent identity, accessible data, consent and risky-agent response. The corpus contains a current SCuBA risky-agent policy, but the older MCSB v1 edition is not an AI security baseline. Further publisher-specific review is needed before creating broad AI claims. |

## How frequency was used

The JSON companion records distinct source records matching each declared topic expression, broken down by framework. It counts neither independent organisations nor unique obligations: parent records, repeated maturity requirements and SCF mappings can repeat concepts. SCF volume is therefore not allowed to determine priority on its own. Specific source UIDs support each candidate.

## Remaining source limitations

- cis-controls: 5 safeguard identifiers were rebuilt from position because the workbook stores them as numbers and cannot tell 3.10 from 3.1
- cis mapping names safeguard 2.8, which the v8 catalogue does not contain; the mapping workbook is v8.1
- cis mapping names safeguard 6.9, which the v8 catalogue does not contain; the mapping workbook is v8.1
- cis mapping names safeguard 7.8, which the v8 catalogue does not contain; the mapping workbook is v8.1
- cis mapping names safeguard 7.9, which the v8 catalogue does not contain; the mapping workbook is v8.1
- cis mapping names safeguard 12.9, which the v8 catalogue does not contain; the mapping workbook is v8.1
- csf: PR.IP is marked withdrawn but names no replacement
- csf: PR.PT is marked withdrawn but names no replacement
- csf: DE.DP is marked withdrawn but names no replacement
- aescsf: 45 references name ISM controls not in the loaded ISM (12 distinct, e.g. ISM-1185, ISM-1388, ISM-1433, ISM-1435, ISM-1651). AESCSF cites the revision current when it was published; these have since been retired.
- pspf: requirement numbers are not contiguous — 113 absent from the published table. Nothing downstream may assume a dense range.
- cirmp-rules: 6 framework-table rows lack resolved links to the required document editions: Australian Standard AS ISO/IEC 27001:2015; Australian Standard AS ISO/IEC 27001:2023; Essential Eight Maturity Model published by the Australian Signals Directorate; Framework for Improving Critical Infrastructure Cybersecurity published by the National Institute of Standards and Technology of the United States of America; The 2020-21 AESCSF Framework Core published by Australian Energy Market Operator Limited (ACN 072 010 327)
- benchmark detail for cis-win11 not extracted; run tools/extract_cis_benchmark.py
- benchmark detail for cis-m365 not extracted; run tools/extract_cis_benchmark.py
- benchmark detail for cis-azure not extracted; run tools/extract_cis_benchmark.py
- benchmark detail for cis-office not extracted; run tools/extract_cis_benchmark.py
- benchmark detail for cis-edge not extracted; run tools/extract_cis_benchmark.py
- benchmark detail for cis-chrome not extracted; run tools/extract_cis_benchmark.py

The warnings above include existing retired/mismatched references and unavailable local CIS benchmark extracts. They are retained visibly rather than converted into invented mappings. The Essential Eight legislation reference needs a separate edition/incorporation review. SCF’s generic NIST R5 mapping has not been transferred to NIST 5.2.0.

Reproduce with `python tools/revalidate_corpus.py`. Run `python tests/run_all.py` for behavioural regression checks.
