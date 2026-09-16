# Publisher sources

WACC does not distribute publisher files. Public sources are downloaded from their
publisher when needed, and files that require a sign-in or an interactive export stay on
the user's machine.

Run this from the repository folder:

```powershell
python -m wacc sources
```

The command downloads public files into `sources/files/`, follows download links on
publisher landing pages where necessary, and verifies the reviewed edition in
`permissions.json`. Files normally require an exact SHA-256 match. For OAG HTML reports,
WACC also accepts the reviewed fingerprint of the full report header and body, including
text, dates, links and image references; rotating website forms and analytics outside the
report are excluded. Changed report content is rejected. Existing matching files are left alone. The
whole directory is ignored by Git and excluded from release packages.

To see every source and acquisition method without downloading anything:

```powershell
python -m wacc sources --list
```

The app's **Sources** page shows available, missing and changed files. **Download missing
public sources and reload** runs acquisition in the background and reloads the corpus
afterwards. Progress and per-file errors remain visible, and repeat clicks do not start
duplicate jobs. This action uses the configured publisher catalogue only.

For an offline status check, run `python -m wacc sources --status`. To import downloads
without renaming each file, run `python -m wacc sources --import-from "C:\path\to\downloads"`.
WACC checks files directly in that folder, copies recognised reviewed files and then
attempts the remaining automatic downloads. Originals and unmatched files are untouched.
The destination respects `WACC_SOURCES`, or `--destination` when supplied.

There are 64 configured automatic routes and 10 manual acquisitions. The live review
verified 59 automatic downloads; four were blocked by their publishers and one requires
an edition review. See [the acquisition review](../docs/source-acquisition-review.md).

To retry or acquire one file:

```powershell
python -m wacc sources --only "Detecting and mitigating Active Directory compromises (September 2026).pdf"
```

## Sources that need manual acquisition

The command prints the applicable instruction for each manual source. In general:

- **CIS Controls and CIS Benchmarks:** download the exact edition from CIS or CIS
  WorkBench, retain the publisher filename shown by `--list`, and keep it local.
- **A specific publisher edition with no stable download URL:** obtain the named edition
  from the publisher and save it under the exact filename shown by `--list`.
- **Files marked `excluded_pending_permission`:** these can be used as local inputs when
  law and the publisher's terms permit, but WACC does not redistribute their files or
  generated text.

After placing a file in `sources/files/`, run:

```powershell
python -m wacc.packaging
```

A hash failure means the bytes differ from the edition reviewed for the corpus. Do not
rename a newer edition to make it look like the expected file. Review the new edition,
update its corpus where needed, and then update the hash and acquisition record.

## Records in this folder

- `permissions.json` records the edition, expected hash, provenance, licence review and
  redistribution decision for each source.
- `acquisition.json` records publisher URLs for automatic downloads and plain-English
  instructions for manual sources.
- `MITRE-ATTACK-LICENSE.txt` preserves the licence notice associated with MITRE ATT&CK
  data.

These records do not relicense publisher material. WACC's source cache is always local,
including when a publisher permits redistribution.

## Cloud frameworks and WA audit context

The acquisition catalogue includes SCF 2026.2, Microsoft Cloud Security Benchmark v1,
the November 2023 Essential Eight model, and a pinned revision of CISA's Microsoft 365
SCuBA baselines. Editions matter: a mapping to an older ISM, CIS or NIST edition is not
automatically transferred to a different edition in WACC.

SCF text is imported unchanged for local reference under its recorded terms. Generated
SCF extracts are excluded from distribution. WACC's technical assessments are separately
authored from their cited guidance; they are not adaptations of SCF control text.

Thirteen OAG report pages are also acquired for local reference. Their HTML and images
are not redistributed. The application provides brief, independently written commentary,
report dates and links to the publisher. Reports inform assessment priorities; their
historical findings do not establish an organisation's present condition.
