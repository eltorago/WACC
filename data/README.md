# Workspace and corpus data

Workspace controls, assessments and mappings are locally authored. Source links identify
the publisher requirement and the part addressed by the control.

Each workspace control also has a **MITRE ATT&CK** section. It names relevant Enterprise
techniques, links to MITRE, and explains whether the control reduces the likelihood of an
attack, helps detect or contain it, supports recovery, or enables another safeguard.
You can search the workspace by technique ID (for example, `T1110.004`), technique name,
or mitigation ID. Search by name requires the ATT&CK source to be loaded.

Mitigation references are checked against Enterprise ATT&CK 19.2. ATT&CK is a trademark
of The MITRE Corporation. See
[MITRE ATT&CK](https://attack.mitre.org/) for the publisher's technique descriptions.

The source browser preserves provenance, framework identity and hierarchy so readers can
return to the relevant publisher record. Source documents retain their own licences and
attribution. See [sources/README.md](../sources/README.md) for automatic downloads, manual
acquisition and edition checks.

## Data files

Paths below are relative to the repository root.

| Path | Purpose |
|---|---|
| `data/library/` | The 84 locally written workspace controls, grouped into one JSON file per topic. |
| `data/department-assessment-policy.json` | Authored assessment prompts and references for 86 WA policy requirement records. |
| `data/local/assessments/` | Private assessments, original log exports, validation runs and review history; excluded from Git and distribution. |
| `data/workspace-attack.json` | Local ATT&CK assessments for every workspace control, including explanations and MITRE mitigation references. |
| `data/workspace-technical*.json` | Check titles, access requirements, evidence, parent controls and publisher references. |
| `data/assessment-procedures.json` | The authoritative steps, commands, expected results and validation record for each technical check. |
| `data/assessment-sources.json` and `data/assessment-source-review.json` | Official command documentation and the recorded source review. |
| `data/workspace-grc-evidence.json` | Specific publisher-listed documents and practical review questions for all 84 controls. |
| `data/workspace-frameworks.json` | Reviewed links from workspace controls to additional source requirements. |
| `data/wa-audit-context.json` | Dated WA audit findings and their relevance to assessments. |
| `data/framework-review.json` | SCF mapping inventory and cloud framework priorities. |
| `data/corpus/` | Curated extracts used when a publisher does not provide a suitable machine-readable source. |
| `data/validation/` | Search expectations and the topic-frequency report used to check coverage and ranking. |

For additions or changes, follow the [framework and assessment authoring guide](../sources/add-framework.md).
Private imports stay under `data/local/`; publisher originals stay in `sources/files/`.
