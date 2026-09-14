# WACC

WA Control Crosswalk. See [running instructions](HOW-TO-RUN.md).

The home page opens a control-centred privileged-access pilot: five controls with
individual assessments, business risks, evidence records and 24 source references.
Framework selection scopes the control list, source references and CSV mapping export.
The full publisher corpus remains available through **Browse source corpus**.

Assessment records are stored per control in the current browser, not on the server.
Use **Download assessment** to retain a JSON copy outside the browser. This pilot does
not yet import records, synchronise them between devices, or calculate framework
compliance. Mapping relationships describe overlap; source-specific conditions still
need assessment. All pilot mappings are locally reviewed, not publisher assertions.

The pilot library is in `data/library/privileged-access.json`. Its assessments are
locally authored and source procedures remain separately attributed. AESCSF anti-patterns
are retained as related context, never treated as desired practices.

Reviewed source files are included under [sources/](sources/README.md), with per-file
permissions, attribution and SHA-256 hashes. This collection is for the existing
private, non-commercial project; some sources have additional distribution limits.
