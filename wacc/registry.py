"""Describe every framework WACC can load and where it appears in the source browser.

This file records publisher, jurisdiction, source file, display order and reuse status.
The loaders use that information to find documents and preserve their identity.

Licence values are conservative working decisions. Material remains import-only until its
reuse terms have been reviewed.
"""

from typing import Dict, List

from .model import (
    Fidelity,
    Framework,
    GuidanceDocument,
    Jurisdiction,
    Level,
    Licence,
    Tier,
)


def _levels(*names: str) -> List[Level]:
    return [Level(key=n.lower().replace(" ", "-"), name=n, depth=i) for i, n in enumerate(names)]


# --------------------------------------------------------------------------
# Tier 1 — statute
# --------------------------------------------------------------------------

FRAMEWORKS: List[Framework] = [
    Framework(
        key="soci-act",
        name="Security of Critical Infrastructure Act 2018",
        short_name="SOCI Act",
        publisher="Commonwealth of Australia",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.STATUTE,
        intra_tier_order=0,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Part", "Division", "Section", "Subsection"),
        source_file="soci-act-latest.docx",
        source_url="https://www.legislation.gov.au/C2018A00029/latest/text",
        notes=[
            "Federal Register of Legislation content is published under CC BY 4.0.",
            "Kept separate from the CIRMP Rules because s 8 means different things in "
            "each instrument and an identifier must resolve to one of them.",
        ],
    ),
    Framework(
        key="cirmp-rules",
        name=(
            "Security of Critical Infrastructure (Critical infrastructure risk "
            "management program) Rules (LIN 23/006) 2023"
        ),
        short_name="CIRMP Rules",
        publisher="Minister for Home Affairs",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.STATUTE,
        intra_tier_order=1,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Part", "Division", "Section", "Subsection"),
        source_file="cirmp-rules-latest.docx",
        source_url="https://www.legislation.gov.au/F2023L00112/latest/text",
        notes=[
            "Latest compilation, not the as-made 2023 text. Amended by LIN 25/011 and "
            "by LIN 26/075, the Enhanced CIRMP Rules made 9 June 2026.",
            "Two framework tables, not one, and they name different documents. s 8(4) "
            "names NIST's 'Framework for Improving Critical Infrastructure "
            "Cybersecurity' — CSF 1.1 under its former title — at Essential Eight "
            "maturity level one and AESCSF Security Profile 1. s 8A(3), the enhanced "
            "requirements for assets specified in s 4A(1), names 'The NIST "
            "Cybersecurity Framework (CSF) 2.0' by that title, at maturity level two "
            "and Security Profile 2.",
            "Both tables incorporate their documents as in force from time to time "
            "under ss 30AN and 30ANA of the Act. Whether that carries CSF 1.1 forward "
            "to CSF 2.0 is a legal question this tool does not answer; it shows which "
            "provision names which document and leaves the reading to the reader.",
        ],
    ),
    # ----------------------------------------------------------------------
    # Tier 2 — mandated policy
    # ----------------------------------------------------------------------
    Framework(
        key="wa-csp",
        name="Western Australian Government Cyber Security Policy 2024",
        short_name="WA CSP",
        publisher="Office of Digital Government, Department of the Premier and Cabinet",
        jurisdiction=Jurisdiction.WA,
        tier=Tier.MANDATED_POLICY,
        intra_tier_order=0,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.IMPORT_ONLY,
        levels=_levels("Function", "Section", "Requirement"),
        source_file="wa-cyber-security-policy.pdf",
        notes=[
            "Licence to be read off the document's copyright page during extraction, "
            "not assumed from WA Government's usual CC BY position.",
        ],
    ),
    Framework(
        key="wa-circular",
        name="Premier's Circular 2025/13 — Cyber Security Measures for WA Government Entities",
        short_name="Premier's Circular",
        publisher="Department of the Premier and Cabinet",
        jurisdiction=Jurisdiction.WA,
        tier=Tier.MANDATED_POLICY,
        intra_tier_order=1,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.IMPORT_ONLY,
        levels=_levels("Measure", "Requirement"),
        source_file="wa-premiers-circular-2025-13.pdf",
        notes=[
            "Read end to end for a licence statement and states none — no copyright "
            "page, no Creative Commons mark. Absence of a statement is not permission, "
            "so it stays import-only alongside the WA CSP.",
            "The instrument that binds. The Policy is the content, the Circular is the "
            "obligation, and it applies to entities in scope of the 2024 Policy.",
            "Two pages. Expect a handful of requirements, not a catalogue.",
        ],
    ),
    Framework(
        key="pspf",
        name="Protective Security Policy Framework — Release 2026 List of Requirements",
        short_name="PSPF",
        publisher="Australian Government",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.MANDATED_POLICY,
        intra_tier_order=0,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Domain", "Section", "Requirement"),
        source_file="pspf-list-of-requirements.pdf",
        revision="Release 2026 (July 2026)",
        revision_source="cover row of the List of Requirements table",
        notes=[
            "The table publishes Mandatory status, applicability, start date and "
            "scoring per requirement. Extract those; infer none of them.",
            "Requirement count comes from the file. The 217 in the original build was "
            "an earlier release and does not carry over.",
        ],
    ),
    # ----------------------------------------------------------------------
    # Tier 3 — outcome and maturity
    # ----------------------------------------------------------------------
    Framework(
        key="oag-wa",
        name="OAG WA Better Practice Guides",
        short_name="OAG WA",
        publisher="Office of the Auditor General for Western Australia",
        jurisdiction=Jurisdiction.WA,
        tier=Tier.OUTCOME,
        intra_tier_order=0,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Guide", "Theme", "Recommendation"),
        attribution=(
            "\u00a9 Office of the Auditor General Western Australia. Reproduced in whole "
            "or in part with the source acknowledged, as the reports' own copyright page "
            "permits."
        ),
        source_files=[
            "Report-12_Digital-Identity-and-Access-Management-Better-Practice-Guide.pdf",
            "Report-24_-Security-Basics-for-Protecting-Critical-Infrastructure-from-Cyber-Threats.pdf",
        ],
        notes=[
            "Tier 3 because these answer what good looks like, not what is required. "
            "The Auditor General audits against them; they do not mandate.",
            "Two guides loaded as one framework, with the report number as an "
            "attribute, so a reader sees one OAG column rather than a column per report.",
            "Licence read off the copyright page of both reports, not assumed: "
            "'All rights reserved. This material may be reproduced in whole or in part "
            "provided the source is acknowledged.' That is an express grant, so OAG text "
            "ships and the acknowledgement ships with it. The packaging test fails if "
            "the attribution is missing.",
        ],
    ),
    Framework(
        key="aescsf",
        name="Australian Energy Sector Cyber Security Framework",
        short_name="AESCSF",
        publisher="AEMO",
        jurisdiction=Jurisdiction.AU_INDUSTRY,
        tier=Tier.OUTCOME,
        intra_tier_order=0,
        fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.IMPORT_ONLY,
        levels=_levels("Domain", "Objective", "Practice"),
        source_file="aescsf-framework-core.xlsx",
        revision="Framework Core V2 (the 2023 edition)",
        revision_source=(
            "the workbook states no edition in any cell; its only sheet is named "
            "'AESCSF Core V2 _ Final-V1-0' and Aidan confirmed V2 is the 2023 edition"
        ),
        notes=[
            "CIRMP s 8(4) names the 2020-21 Framework Core and s 8A(3) names the 2023 "
            "Framework Core. They are different documents, so only s 8A(3) links here. "
            "Whether s 8(4)'s reference carries forward under 'as in force from time to "
            "time' is a question about the instrument, not about this corpus.",
            "Practice text never ships. Importer only, and the packaging test fails "
            "the build if the workbook or a generated copy of its text would be "
            "included.",
            "Assessed at practice level and reported at domain level, so both "
            "granularities are kept.",
        ],
    ),
    Framework(
        key="csf",
        name="NIST Cybersecurity Framework 2.0",
        short_name="CSF 2.0",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.OUTCOME,
        intra_tier_order=0,
        fidelity=Fidelity.OFFICIAL_MACHINE_READABLE,
        licence=Licence.SHIPPABLE,
        levels=_levels("Function", "Category", "Subcategory"),
        source_file="nist-csf-2.0-cprt-all-olir.xlsx",
        published="2024-02-26",
        notes=[
            "Corpus comes from NIST's CPRT export, which carries the OLIR informative "
            "references with it. Control text is never taken from the CSWP 29 PDF.",
            "Named in CIRMP Rules s 8(4), which is what puts an American outcome "
            "framework inside an Australian obligation chain.",
        ],
    ),
    Framework(
        key="c2m2",
        name="Cybersecurity Capability Maturity Model, Version 2.1",
        short_name="C2M2",
        publisher="US Department of Energy",
        jurisdiction=Jurisdiction.US,
        tier=Tier.OUTCOME,
        intra_tier_order=2,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        attribution=(
            "© 2022 Carnegie Mellon University. This version of C2M2 is being released "
            "and maintained by the U.S. Department of Energy."
        ),
        levels=_levels("Domain", "Objective", "Practice"),
        source_file="C2M2 Version 2.1 June 2022.pdf",
        revision="Version 2.1",
        revision_source="running header on every page and section 4.1",
        published="2022-06",
        notes=[
            "356 practices across 10 domains, which is what the document states about "
            "itself in section 4.1. The extractor is checked against that figure rather "
            "than against a tolerance.",
            "The maturity indicator level is carried as a publisher tag on every "
            "practice. It is the operative half of what the CIRMP Rules require — "
            "s 8(4) names C2M2 at MIL1 and s 8A(3) names Version 2.1 at MIL2 — so a "
            "practice without its level cannot be read against either provision.",
            "Shippable with attribution. The NOTICE page states that the US Government "
            "has unlimited rights to reproduce and display this version 'as well as the "
            "right to authorize others, and hereby authorizes others, to do the same'. "
            "Read off the document's own last page, not assumed.",
            "The document's own Cautionary Note says the guidance 'is not part of any "
            "regulatory framework and is not intended for regulatory use'. The CIRMP "
            "Rules name it regardless; both statements are true and the tool reports "
            "each of them rather than reconciling them.",
            "Shares its domain abbreviations with the AESCSF — ACCESS, ASSET, THREAT "
            "and the rest — because the AESCSF was built on this model. No link between "
            "them is stored: neither publisher states a practice-level mapping here, so "
            "one would be this tool's judgement wearing AEMO's name.",
        ],
    ),
    Framework(
        key="ztmm",
        name="CISA Zero Trust Maturity Model Version 2.0",
        short_name="ZTMM",
        publisher="CISA",
        jurisdiction=Jurisdiction.US,
        tier=Tier.OUTCOME,
        intra_tier_order=1,
        fidelity=Fidelity.STRUCTURED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Pillar", "Function"),
        source_file="zero_trust_maturity_model_v2_508.pdf",
        published="2023-04",
        notes=[
            "Loaded one row per function, with the four maturity stages carried as "
            "publisher tags. The document describes what an agency looks like at each "
            "stage rather than stating a control, which is why it sits at tier 3 beside "
            "the CSF and the AESCSF rather than in a catalogue.",
            "No Australian instrument names this document, and CISA wrote it for US "
            "federal agencies. It is here because it is the reference point a zero "
            "trust question is asked against, not because anything requires it.",
            "Marked TLP:CLEAR on every page, which is the document stating its own "
            "distribution terms.",
        ],
    ),
    # ----------------------------------------------------------------------
    # Tier 4 — control catalogue
    # ----------------------------------------------------------------------
    Framework(
        key="ism",
        name="Information Security Manual",
        short_name="ISM",
        publisher="Australian Signals Directorate",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.CATALOGUE,
        intra_tier_order=0,
        fidelity=Fidelity.OFFICIAL_MACHINE_READABLE,
        licence=Licence.SHIPPABLE,
        levels=_levels("Chapter", "Section", "Control"),
        source_file="ISM_catalog.json",
        source_url="https://www.cyber.gov.au/ism/oscal",
        revision="2026.09.4",
        revision_source="OSCAL metadata version field",
        published="2026-09-03",
        notes=[
            "ASD's own GitHub mirror of the OSCAL release.",
            "Essential Eight maturity ships as published baseline profiles "
            "(E8_ML1/ML2/ML3), so maturity is a publisher tag, never inferred.",
            "Applicability is a list of classification levels, not a sentence.",
        ],
    ),
    Framework(
        key="nist-800-53",
        name="NIST SP 800-53 Security and Privacy Controls",
        short_name="800-53",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.CATALOGUE,
        intra_tier_order=0,
        fidelity=Fidelity.OFFICIAL_MACHINE_READABLE,
        licence=Licence.SHIPPABLE,
        levels=_levels("Family", "Control", "Enhancement"),
        source_file="NIST_SP-800-53_rev5_catalog.json",
        revision="Rev 5.2.0",
        revision_source="OSCAL metadata version field",
        notes=[
            "The OSCAL catalog carries SP 800-53A Rev 5.2.0 assessment procedures as "
            "assessment-objective and assessment-method parts. 800-53A is therefore an "
            "attribute on the control, not a corpus of its own, and its procedures are "
            "labelled as NIST's.",
            "800-53B baselines load as published profiles and become a low/moderate/"
            "high tag, the direct analogue of an Essential Eight maturity level.",
        ],
    ),
    Framework(
        key="cis-controls",
        name="CIS Critical Security Controls Version 8",
        short_name="CIS Controls",
        publisher="Center for Internet Security",
        jurisdiction=Jurisdiction.INTERNATIONAL,
        tier=Tier.CATALOGUE,
        intra_tier_order=0,
        fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.IMPORT_ONLY,
        levels=_levels("Control", "Safeguard"),
        source_file="CIS_Controls_Version_8.xlsx",
        notes=[
            "Loaded as a catalogue in its own right, and as the bridge that makes CIS "
            "benchmark detail citable: benchmark recommendation names a safeguard, and "
            "CIS's own mapping takes the safeguard to an Essential Eight mitigation, "
            "which ASD's ISM profiles take to ISM controls. Three published hops "
            "where there was previously a subject match.",
            "The mapping workbook is v8.1 and the catalogue is v8. Safeguard "
            "identifiers are compared at load, and any that do not line up are "
            "reported rather than assumed equivalent.",
            "Import only. CIS terms restrict redistribution, so no CIS text ships.",
        ],
    ),
    # ----------------------------------------------------------------------
    # Tier 5 — technical specification
    # ----------------------------------------------------------------------
    Framework(
        key="asd-ad",
        name="Detecting and Mitigating Active Directory Compromises",
        short_name="ASD AD",
        publisher="Australian Signals Directorate",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.SPECIFICATION,
        intra_tier_order=0,
        fidelity=Fidelity.CURATED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Checklist", "Technique", "Mitigation"),
        source_file="Detecting and mitigating Active Directory compromises (September 2026).pdf",
        source_url=(
            "https://www.cyber.gov.au/business-government/detecting-responding-to-threats/"
            "detecting-and-mitigating-active-directory-compromises"
        ),
        revision="September 2026",
        revision_source="publisher attachment title and publication copyright page",
        notes=[
            "The 2026 edition adds Shadow Credentials controls and changes the DCSync "
            "permission review and planned KRBTGT rotation intervals to six months.",
            "Its checklist states concrete AD hardening measures, so WACC loads it as "
            "technical control detail rather than general guidance.",
        ],
    ),
    Framework(
        key="nist-800-63",
        name="NIST SP 800-63 Digital Identity Guidelines",
        short_name="800-63",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.SPECIFICATION,
        intra_tier_order=0,
        fidelity=Fidelity.CURATED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Volume", "Section", "Normative statement"),
        source_files=[
            "sp800-63.html",
            "sp800-63a.html",
            "sp800-63b.html",
            "sp800-63c.html",
        ],
        notes=[
            "Volumes 63A, 63B and 63C in one framework, identifiers prefixed by "
            "volume. Three columns of digital identity would crowd out the rest of "
            "tier 5 for no gain.",
            "800-53 IA-12 cites 800-63A by name, so identity proofing links are "
            "published rather than derived.",
            "Extracted as normative statements with section references, not "
            "transcribed whole.",
        ],
    ),
    Framework(
        key="nist-800-131a",
        name="NIST SP 800-131A Transitioning Cryptographic Algorithms and Key Lengths",
        short_name="800-131A",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.SPECIFICATION,
        intra_tier_order=1,
        fidelity=Fidelity.CURATED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Algorithm class", "Transition statement"),
        source_file="NIST.SP.800-131Ar2.pdf",
        notes=[
            "Rev 2 final is the corpus. Rev 3 initial public draft attaches to the "
            "same parameters as a proposed change and never as a requirement.",
        ],
    ),
    Framework(
        key="nist-800-57pt1",
        name="NIST SP 800-57 Part 1 Recommendation for Key Management",
        short_name="800-57 Pt1",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.SPECIFICATION,
        intra_tier_order=2,
        fidelity=Fidelity.CURATED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Topic", "Parameter statement"),
        source_file="nist.sp.800-57pt1r5.pdf",
        revision="Revision 5",
        revision_source="cover page",
        notes=[
            "Rev 6 is an initial public draft and is not loaded.",
            "Footnote markers render as plain digits in the extracted text. Those "
            "welded onto a time unit are removed, because '< 2 years61' hid a stated "
            "cryptoperiod from every comparison. One welded onto an algorithm name is "
            "left as it is — Table 2 reads '3TDEA68' — because AES-128 and SHA3-256 "
            "are names with digits in them and no rule separates the two safely.",
        ],
    ),
    Framework(
        key="nist-800-88",
        name="NIST SP 800-88 Guidelines for Media Sanitization",
        short_name="800-88",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        tier=Tier.SPECIFICATION,
        intra_tier_order=3,
        fidelity=Fidelity.CURATED_EXTRACT,
        licence=Licence.SHIPPABLE,
        levels=_levels("Media type", "Sanitization statement"),
        source_file="NIST.SP.800-88r2.pdf",
        revision="Revision 2",
        revision_source="cover page",
        notes=[
            "Revision 2, which supersedes the Rev 1 named in the brief.",
            "800-53 MP-6 cites 800-88 directly, so media disposal links are published.",
        ],
    ),
]


FRAMEWORKS.extend([
    Framework(key='asd-principles',name='ASD Cyber Security Principles',short_name='ASD Cyber Security Principles',
        publisher='Australian Signals Directorate',jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.OUTCOME,intra_tier_order=0,fidelity=Fidelity.OFFICIAL_MACHINE_READABLE,
        licence=Licence.SHIPPABLE,revision='September 2026',levels=_levels('Principle'),
        published='2026-09-03',retrieved='2026-09-17',
        revision_source='ASD principles page and September 2026 attachment; statements verified against ISM OSCAL 2026.09.4',
        source_file='ISM_catalog.json',source_files=['asd-cyber-security-principles-2026-09.html'],
        source_url='https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/ism/cyber-security-principles',
        attribution='Australian Signals Directorate, Commonwealth of Australia 2026. CC BY 4.0. Principle titles, identifiers and statements preserved; workspace mappings are WACC additions.',
        notes=['49 principles across Govern, Identify, Protect, Detect, Respond and Recover.',
               'Loaded from the ISM-principle class in the official ISM OSCAL catalogue and displayed once in this separate framework.']),
    Framework(key='asd-strategies',name='ASD Strategies to Mitigate Cyber Security Incidents',short_name='ASD mitigation strategies',
        publisher='Australian Signals Directorate',jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.CATALOGUE,intra_tier_order=2,fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.SHIPPABLE,revision='February 2017',levels=_levels('Strategy'),
        revision_source='Publisher last-updated date and February 2017 attachment edition',
        source_file='asd-strategies-2017.html',
        source_url='https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/mitigating-cyber-security-incidents/strategies-to-mitigate-cybersecurity-incidents',
        attribution='Australian Signals Directorate, Commonwealth of Australia 2017. CC BY 4.0. Strategy wording preserved; WACC adds row locators and local mappings.',
        notes=['37 strategies in five categories. S01-S37 are WACC locators, not ASD identifiers.',
               'February 2017 edition: legacy software references and thresholds are historical. Current ISM and Essential Eight requirements must be assessed separately.']),
    Framework(key='scuba',name='CISA SCuBA Microsoft 365 security baselines',short_name='SCuBA M365',
        publisher='CISA',jurisdiction=Jurisdiction.US,tier=Tier.SPECIFICATION,intra_tier_order=1,
        fidelity=Fidelity.PUBLISHER_IMPORT,licence=Licence.SHIPPABLE,
        levels=_levels('Policy'),revision_source='Pinned ScubaGear commit and baseline policy version identifiers',
        revision='ScubaGear 2f8c824 (reviewed September 2026)',source_file='scuba-m365-baselines.zip',
        source_url='https://github.com/cisagov/ScubaGear/tree/2f8c8241a5753a83a502d06688ce82081023dd0a/PowerShell/ScubaGear/baselines',
        attribution='CISA SCuBA. Includes Microsoft documentation adapted by CISA under CC BY 4.0; original sources and licence notices are retained in the linked baseline documents.',
        notes=['US federal baseline; informative for WA entities. Original SHALL wording does not establish a WA obligation.',
               'Imports seven current baselines and excludes superseded Defender and removed-policy documents.']),
    Framework(key='scf',name='Secure Controls Framework 2026.2',short_name='SCF',
        publisher='Secure Controls Framework Council',jurisdiction=Jurisdiction.INTERNATIONAL,
        tier=Tier.CATALOGUE,intra_tier_order=10,fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.IMPORT_ONLY,revision='2026.2',
        levels=_levels('Control'),revision_source='Workbook filename and SCF 2026.2 worksheet',
        source_file='secure-controls-framework-scf-2026-2.xlsx',
        source_url='https://github.com/securecontrolsframework/securecontrolsframework',
        attribution='Secure Controls Framework (SCF), SCF Council, CC BY-ND 4.0. Control wording imported without alteration. https://securecontrolsframework.com/terms-and-conditions',
        notes=['SCF is a meta-framework. Its mappings are assertions by SCF, not endorsements by the target publishers.',
               'Local import only. CC BY-ND 4.0 restricts distribution of adapted SCF material. WACC technical checks are authored independently from ACSC and Microsoft guidance.']),
    Framework(key='essential-eight',name='ASD Essential Eight maturity model',short_name='Essential Eight',
        publisher='Australian Signals Directorate',jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        tier=Tier.OUTCOME,intra_tier_order=5,fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.SHIPPABLE,revision='November 2023',
        levels=_levels('Requirement'),revision_source='Publisher page last-updated date and maturity model edition heading',
        source_file='essential-eight-maturity-model.html',
        source_url='https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight/essential-eight-maturity-model',
        attribution='Australian Signals Directorate, Commonwealth of Australia 2023. CC BY 4.0.',
        notes=['Imported from the publisher tables. Row identifiers are WACC locators, not ASD-issued control identifiers.']),
    Framework(key='mcsb',name='Microsoft cloud security benchmark v1',short_name='MCSB v1',
        publisher='Microsoft',jurisdiction=Jurisdiction.INTERNATIONAL,
        tier=Tier.CATALOGUE,intra_tier_order=11,fidelity=Fidelity.PUBLISHER_IMPORT,
        licence=Licence.SHIPPABLE,revision='v1',source_file='Microsoft_cloud_security_benchmark_v1.xlsx',
        levels=_levels('Control'),revision_source='Publisher workbook filename and Readme worksheet',
        source_url='https://learn.microsoft.com/en-us/security/benchmark/azure/overview-mcsb-v1',
        attribution='Microsoft and contributors. Microsoft Cloud Security Benchmark v1. CC BY 4.0. https://github.com/MicrosoftDocs/SecurityBenchmarks/blob/master/LICENSE',
        notes=['The complete v1 workbook is imported. Microsoft also publishes v2 preview guidance; this import does not claim v2 coverage.'])
])

FRAMEWORKS_BY_KEY: Dict[str, Framework] = {f.key: f for f in FRAMEWORKS}


# --------------------------------------------------------------------------
# Configuration detail sources — attached to test procedures, never columns
# --------------------------------------------------------------------------

DETAIL_SOURCES: List[Dict[str, object]] = [
    {
        "key": "cis-win11",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "operating system", "workstation", "desktop", "endpoint", "end user device",
            "microsoft windows", "windows",
        ],
        "title": "CIS Microsoft Windows 11 Stand-alone Benchmark v5.0.0",
        "platform": "Windows 11",
        "file": "CIS_Microsoft_Windows_11_Stand-alone_Benchmark_v5.0.0.pdf",
        "expected": 488,
    },
    {
        "key": "cis-m365",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "microsoft 365", "office 365", "cloud service", "saas", "tenant",
            "email client", "collaboration",
        ],
        "title": "CIS Microsoft 365 Foundations Benchmark v7.0.0",
        "platform": "Microsoft 365",
        "file": "CIS_Microsoft_365_Foundations_Benchmark_v7.0.0.pdf",
        "expected": 160,
    },
    {
        "key": "cis-azure",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "azure", "cloud service", "iaas", "paas", "tenant", "cloud platform",
        ],
        "title": "CIS Microsoft Azure Foundations Benchmark v6.0.0",
        "platform": "Microsoft Azure",
        "file": "CIS_Microsoft_Azure_Foundations_Benchmark_v6.0.0.pdf",
        "expected": 127,
    },
    {
        "key": "cis-office",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "office productivity suite", "microsoft office", "macro", "document",
            "spreadsheet", "email client",
        ],
        "title": "CIS Microsoft Office Enterprise Benchmark v1.2.0",
        "platform": "Microsoft Office",
        "file": "CIS_Microsoft_Office_Enterprise_Benchmark_v1.2.0.pdf",
        "expected": 241,
    },
    {
        "key": "cis-edge",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "web browser", "browser", "microsoft edge",
        ],
        "title": "CIS Microsoft Edge Benchmark v4.0.0",
        "platform": "Microsoft Edge",
        "file": "CIS_Microsoft_Edge_Benchmark_v4.0.0.pdf",
        "expected": 139,
    },
    {
        "key": "cis-chrome",
        # What this benchmark is a benchmark of. A recommendation reaches a control
        # only when the control names the product class, because word overlap alone
        # cannot know that Chrome is a browser: it offered a minimum password age
        # setting against "Web browser security settings cannot be changed".
        "covers": [
            "web browser", "browser", "google chrome", "chrome",
        ],
        "title": "CIS Google Chrome Benchmark v3.0.0",
        "platform": "Google Chrome",
        "file": "CIS_Google_Chrome_Benchmark_v3.0.0.pdf",
        "expected": 118,
    },
]


# --------------------------------------------------------------------------
# Guidance layer — named and linked, never turned into controls
# --------------------------------------------------------------------------

GUIDANCE: List[GuidanceDocument] = [
    GuidanceDocument(
        key="asd-secure-by-design",
        title="Secure by Design Foundations (July 2024)",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Twenty pages built around Foundations, each with Key Risks, Key Focus Areas "
            "and Key Benefits set out separately for technology manufacturers and "
            "technology consumers. No RFC 2119 keyword and no numbered requirement. It "
            "says what a manufacturer should be doing, which is context for a supply "
            "chain finding rather than something a WA entity implements."
        ),
        source_file="Secure by Design foundations (July 2024).pdf",
        relates_to=["ism", "cis-controls", "csf"],
    ),
    GuidanceDocument(
        key="asd-choosing-technologies",
        title="Choosing Secure and Verifiable Technologies (December 2024)",
        publisher="ASD with international partners",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Procurement advice. Its tables pair a threat actor's possible action with "
            "possible mitigation strategies, which are worked examples rather than "
            "requirements, and the rest is narrative on reputation, threat modelling and "
            "what to ask a manufacturer. Useful beside a supply chain control; not one."
        ),
        source_file="Choosing secure and verifiable technologies (December 2024).pdf",
        relates_to=["ism", "pspf", "aescsf", "csf"],
    ),
    GuidanceDocument(
        key="cisa-vulnerability-review",
        title="CISA Vulnerability Review FY2024-2025",
        publisher="CISA",
        jurisdiction=Jurisdiction.US,
        reason=(
            "A statistics report on CWE trends and what they say about software quality. "
            "It states no requirement for any entity, and its figures are a snapshot of "
            "two fiscal years that will age. It points at two documents the corpus does "
            "not hold — CISA Binding Operational Directive 26-04 and the Cybersecurity "
            "Performance Goals 2.0 — and neither binds a WA entity."
        ),
        source_file="cisa-vulnerability-review-fy-2024-2025-508.pdf",
        relates_to=["ism", "cis-controls"],
    ),
    GuidanceDocument(
        key="asd-defensible-architecture",
        title="Foundations for Modern Defensible Architecture",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Forty-seven pages of architectural reasoning with no RFC 2119 keyword and "
            "no numbered requirement anywhere in it. Its tables are illustrations. It "
            "explains how ASD wants the ISM's controls assembled, which is context for "
            "a finding rather than a thing to be complied with."
        ),
        source_file="foundations-for-modern-defensible-architecture.pdf",
        relates_to=["ism", "asd-ad"],
    ),
    GuidanceDocument(
        key="asd-network-segmentation",
        title="Implementing Network Segmentation and Segregation (October 2021)",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Seven pages of narrative on segmentation approaches. States no parameter "
            "and names no control; the ISM holds the requirements it discusses."
        ),
        source_file="Implementing network segmentation and segregation (October 2021).pdf",
        relates_to=["ism"],
    ),
    GuidanceDocument(
        key="asd-lateral-movement",
        title="Preventing Lateral Movement",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Ten pages of narrative. Overlaps the Active Directory compromise guidance "
            "already loaded at tier 5, which does state discrete mitigations; this one "
            "does not."
        ),
        source_file="preventing-lateral-movement.pdf",
        relates_to=["ism", "asd-ad"],
    ),
    GuidanceDocument(
        key="asd-what-to-log",
        title="What Exactly Should We Be Logging?",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Organised by MITRE ATT&CK tactic and explicitly declines to give a list: "
            "it says a list of logging sources is not helpful because knowledge of the "
            "environment is what matters. Extracting requirements from a document that "
            "states it is not stating any would be inventing them."
        ),
        source_file="What-exactly-should-we-be-logging.pdf",
        relates_to=["ism", "csf", "cis-controls"],
    ),
    GuidanceDocument(
        key="joint-lotl",
        title=(
            "Joint Guidance: Identifying and Mitigating Living Off the Land Techniques"
        ),
        publisher="CISA, NSA, FBI, ASD and partner agencies",
        jurisdiction=Jurisdiction.INTERNATIONAL,
        reason=(
            "Forty-six pages of detection advice from eight agencies. Its tables are "
            "worked examples of command lines and log entries rather than requirements."
        ),
        source_file="Joint-Guidance-Identifying-and-Mitigating-LOTL508.pdf",
        relates_to=["ism", "csf", "cis-controls"],
    ),
    GuidanceDocument(
        key="ncsc-ot-connectivity",
        title="Secure Connectivity for Operational Technology",
        publisher="UK NCSC",
        jurisdiction=Jurisdiction.INTERNATIONAL,
        reason=(
            "Built around named principles with narrative bodies rather than testable "
            "statements, and its forty-nine detected tables are page furniture, not "
            "data. The principles are worth citing beside an OT finding; they are not "
            "controls and no Australian instrument names this document."
        ),
        source_file="NCSC-Secure-Connectivity-for-Operational-Technology.pdf",
        relates_to=["aescsf", "ism"],
    ),
    GuidanceDocument(
        key="easm-buyers-guide",
        title="External Attack Surface Management Buyer's Guide",
        publisher="ASD",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "A procurement aid. It states what to ask a vendor, not what an entity must "
            "do, and nothing in it belongs in a control finding."
        ),
        source_file="External-attack-surface-management-EASM-buyers-guide.pdf",
        relates_to=["ism"],
    ),
    GuidanceDocument(
        key="fips-140-3",
        title="FIPS 140-3 Security Requirements for Cryptographic Modules",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "Eleven pages that adopt ISO/IEC 19790 and ISO/IEC 24759 by reference. Its "
            "only table lists the NIST publications that modify those ISO standards, so "
            "the document states no parameter of its own. It is what an ISM "
            "evaluated-product control points at, which is a link rather than a control."
        ),
        source_file="NIST.FIPS.140-3.pdf",
        relates_to=["ism", "nist-800-131a", "nist-800-88"],
    ),
    GuidanceDocument(
        key="nist-800-92",
        title="SP 800-92 Guide to Computer Security Log Management",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "The 2006 original is still the current final and states no retention period "
            "or threshold in a form that survives extraction; its tables are log-source "
            "examples. Rev 1 remains a draft. Loading twenty-year-old numbers as current "
            "parameters would age badly in a finding."
        ),
        source_file="nist-sp-800-92.pdf",
        relates_to=["ism", "csf"],
    ),
    GuidanceDocument(
        key="nist-800-34",
        title="SP 800-34 Rev 1 Contingency Planning Guide for Federal Information Systems",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "Its RTO and RPO figures appear inside worked examples of a fictional "
            "organisation rather than as stated parameters, so extracting them would "
            "present an illustration as a requirement."
        ),
        source_file="nistspecialpublication800-34r1.pdf",
        relates_to=["ism", "csf"],
    ),
    GuidanceDocument(
        key="cisc-cirmp-guidance",
        title="Guidance for the Critical Infrastructure Risk Management Program",
        publisher="Cyber and Infrastructure Security Centre",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Explains how the Rules apply. It states no obligation of its own, so it "
            "informs how tier 1 is structured rather than becoming controls."
        ),
        source_file="cisc-cirmp-guidance.pdf",
        relates_to=["cirmp-rules", "soci-act"],
    ),
    GuidanceDocument(
        key="pspf-guidelines-2026",
        title="PSPF Release 2026 Guidelines",
        publisher="Australian Government",
        jurisdiction=Jurisdiction.AU_COMMONWEALTH,
        reason=(
            "Three hundred and twenty pages of how-to for requirements that are "
            "already loaded from the List of Requirements. Loading both would state "
            "each requirement twice at different strengths."
        ),
        source_file="pspf-release-2026-guidelines.pdf",
        relates_to=["pspf"],
    ),
    GuidanceDocument(
        key="nist-cswp-29",
        title="The NIST Cybersecurity Framework (CSF) 2.0",
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "The narrative document behind CSF 2.0. Corpus text comes from NIST's "
            "machine-readable export instead, so this is the citation, not the source."
        ),
        source_file="nist-cswp-29-csf-2.0.pdf",
        relates_to=["csf"],
    ),
    GuidanceDocument(
        key="nist-800-61r3",
        title=(
            "SP 800-61r3 Incident Response Recommendations and Considerations "
            "for Cybersecurity Risk Management: A CSF 2.0 Community Profile"
        ),
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "A CSF 2.0 Community Profile, which the brief excludes from the corpus. It "
            "is read for the CSF outcomes NIST asserts apply to incident response, so "
            "it yields published links into CSF and no controls of its own. It states "
            "no notification timeframes."
        ),
        source_file="NIST.SP.800-61r3.pdf",
        relates_to=["csf"],
    ),
    GuidanceDocument(
        key="nist-800-18r2",
        title=(
            "SP 800-18r2 Developing Security, Privacy, and Cybersecurity Supply Chain "
            "Risk Management Plans for Systems"
        ),
        publisher="NIST",
        jurisdiction=Jurisdiction.US,
        reason=(
            "Process guidance for writing a system security plan. Cited by 800-53 PL-2, "
            "but states no number, period or threshold an Australian framework also "
            "states, so it fails the tier-5 test that matters."
        ),
        source_file="NIST.SP.800-18r2.pdf",
        relates_to=["nist-800-53"],
    ),
    GuidanceDocument(
        key="cis-ad-guide",
        title="CIS Active Directory and Group Policy Management Best Practices",
        publisher="Center for Internet Security",
        jurisdiction=Jurisdiction.INTERNATIONAL,
        reason=(
            "Narrative best practice with no numbered recommendations and no profile "
            "applicability blocks, unlike the six CIS benchmarks. Nothing to attach to "
            "a test procedure."
        ),
        source_file="CIS_Benchmarks__Active_Directory_Guide__2024_11.pdf",
        relates_to=["asd-ad", "ism"],
    ),
]


from .wa_audit_context import REPORTS as WA_AUDIT_REPORTS

GUIDANCE.extend(GuidanceDocument(key=r['key'],title=r['title'],
    publisher='Office of the Auditor General Western Australia',jurisdiction=Jurisdiction.WA,
    reason=r['date']+' | '+r['sector']+'. Historical audit context. '+r['finding'],
    url=r['url'],relates_to=['oag-wa']) for r in WA_AUDIT_REPORTS)
GUIDANCE.append(GuidanceDocument(key='asd-cloud-blueprint',title="ASD Blueprint for Secure Cloud",
    publisher='Australian Signals Directorate',jurisdiction=Jurisdiction.AU_COMMONWEALTH,
    reason='Microsoft cloud implementation guidance; tailor to the entity and verify effective settings.',
    url='https://blueprint.asd.gov.au/configuration/',relates_to=['ism','mcsb','scuba']))

GUIDANCE_BY_KEY: Dict[str, GuidanceDocument] = {g.key: g for g in GUIDANCE}
