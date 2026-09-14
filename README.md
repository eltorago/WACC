# WACC

WA Control Crosswalk. See [running instructions](HOW-TO-RUN.md).

The home page opens a control-centred library: 13 controls across privileged access, backup and recovery,
vulnerability management and security monitoring, with
individual assessments, business risks, evidence records and 57 source references.
Framework selection scopes the control list, source references and CSV mapping export.
The full publisher corpus remains available through **Browse source corpus**.

Assessment records are stored per control in the current browser, not on the server.
Use **Download assessment** to retain a JSON copy outside the browser. Use **Restore assessment** to load a downloaded record for the same control,
then confirm replacement. Records are not synchronised between devices, and control
results do not calculate framework compliance. Mapping relationships describe overlap; source-specific conditions still
need assessment. All library mappings are locally reviewed, not publisher assertions.

The library is in the topic files under `data/library/`. Its assessments are
locally authored and source procedures remain separately attributed. AESCSF anti-patterns
are retained as related context, never treated as desired practices.

Reviewed source files are included under [sources/](sources/README.md), with per-file
permissions, attribution and SHA-256 hashes. This collection is for the existing
private, non-commercial project; some sources have additional distribution limits.
