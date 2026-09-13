# WACC — running it on the work machine

Python 3.9 or later, standard library only. Nothing here installs anything and nothing
here reaches the network.

## Point it at the source documents

Reviewed publisher files now ship in `sources/files/`. See
[source permissions](sources/README.md) for the included editions and restrictions.
From the repository folder, use the bundled collection in PowerShell:

```powershell
$env:WACC_SOURCES = (Resolve-Path .\sources\files).Path
python -m wacc search "multi-factor authentication"
```

You can instead point `WACC_SOURCES` at your larger local source collection:

```
set WACC_SOURCES=C:\Users\aidan\Desktop\Claude\WA Control Crosswalk
python -m wacc search "multi-factor authentication"
```

A flat folder is supported; subfolders are used when they are there. Actual coverage
depends on the supplied files and installed extracts; missing sources are reported.

To make it permanent rather than per-session, set it once in System Properties →
Environment Variables, or put the `set` line in a one-line `wacc.cmd` beside this file.

## What is still missing after that, and why

| Framework | Why | What would fix it |
|---|---|---|
| WA CSP | The extract is import-only and cannot ship. `data/corpus/wa-csp.json` from the earlier build is still in place, so it loads | nothing, unless the corpus folder is cleared |
| Premier's Circular | Same | same |

Every result names whatever did not load, under **NOT IN THIS BUILD**, with the reason.
A framework that is absent is never drawn as a framework that said nothing — those are
different answers and the tool keeps them apart.

## Commands

```
python -m wacc search "how quickly must an incident be reported"
python -m wacc control ISM-1683
python -m wacc export "backups" --format csv > backups.csv
python -m wacc serve                 # localhost only; it refuses any other host
python -m wacc layout                # the column arithmetic, at three widths
```

## The tests

```
python tests/run_all.py
```

Six layers, lowest first, because a vocabulary defect breaks search, search breaks the
payload and the payload breaks every renderer. Two suites — `test_packaging.py` and
`test_extracts.py` — check the development tree rather than an installed copy and will
report failures here, since they assert that the source documents and the excluded
directories are present.

```
python tests/run_all.py --injected
```

Puts each recorded defect back, one at a time, and checks that a named case fails. Takes
about four minutes. This is the check that says the suite is still watching rather than
merely passing.
