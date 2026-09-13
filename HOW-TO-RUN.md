# WACC — running it on the work machine

Python 3.9 or later, standard library only. Nothing here installs anything and nothing
here reaches the network.

## Point it at the source documents

The publishers' own files never ship with the tool — that is enforced by a test — so a
fresh copy loads nine of the eighteen frameworks and tells you which nine it is missing.
The other nine load straight from the files already sitting in the folder above this one.

```
set WACC_SOURCES=C:\Users\aidan\Desktop\Claude\WA Control Crosswalk
python -m wacc search "multi-factor authentication"
```

With that set, sixteen of the eighteen load. A flat folder is fine; subfolders are used
when they are there.

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
