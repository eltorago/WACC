# Publisher sources

WACC does not distribute publisher files. Public sources are downloaded from their
publisher when needed, and files that require a sign-in or an interactive export stay on
the user's machine.

Run this from the repository folder:

```powershell
python -m wacc sources
```

The command downloads public files into `sources/files/`, follows download links on
publisher landing pages where necessary, and accepts a file only when its SHA-256 matches
the reviewed edition in `permissions.json`. Existing matching files are left alone. The
whole directory is ignored by Git and excluded from release packages.

To see every source and acquisition method without downloading anything:

```powershell
python -m wacc sources --list
```

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
