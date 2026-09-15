# Running WACC locally

WACC runs with Python 3.9 or later and the Python standard library. There is no package
installation step and the application does not download data while it runs.

## Start the web application

Open PowerShell in the repository folder and run:

```powershell
$env:WACC_SOURCES = (Resolve-Path .\sources\files).Path
python -m wacc serve
```

When the terminal reports that WACC is ready, open
[http://127.0.0.1:8765/](http://127.0.0.1:8765/). Keep the PowerShell window open while you
use the application. Press `Ctrl+C` in that window to stop it.

The server binds to `127.0.0.1`, so it is visible only on the computer where it is running.

## Use a different source folder

The repository includes reviewed source documents in `sources/files/`. To use a separate
local collection instead, point `WACC_SOURCES` to that folder before starting WACC:

```powershell
$env:WACC_SOURCES = 'C:\path\to\your\source documents'
python -m wacc serve
```

WACC accepts a flat folder or a folder containing subfolders. It reports any framework it
cannot load rather than presenting that framework as having no relevant controls.

## Command-line examples

The same corpus can be used without the web interface:

```powershell
python -m wacc search "multi-factor authentication"
python -m wacc control ISM-1683
python -m wacc export "backups" --format csv --out backups.csv
python -m wacc build
```

| Command | What it does |
|---|---|
| `search` | Finds related controls and requirements for a subject. |
| `control` | Opens one publisher control by identifier. |
| `export` | Writes search results as CSV or Markdown. |
| `serve` | Starts the local web application. |
| `build` | Loads every available framework and reports warnings. |
| `layout` | Shows the calculated source-browser layout at supported widths. |

Run `python -m wacc` to see the full command help.

## Run the checks

```powershell
python tests\run_all.py
```

The suite checks source permissions, corpus loading, identifier lookup, search quality,
control relationships, assessment content, exports and web rendering. The optional
injected-regression run deliberately restores previously found defects and confirms that
the relevant test detects each one:

```powershell
python tests\run_all.py --injected
```

## Common problems

- **`No module named wacc`** — run the command from the repository folder containing the
  `wacc` directory.
- **A framework is reported as unavailable** — confirm `WACC_SOURCES` points to the folder
  containing the required publisher file.
- **Port 8765 is already in use** — stop the earlier WACC terminal with `Ctrl+C`, or start
  this instance with another port, such as `python -m wacc serve --port 8766`.
- **The page shows older controls** — stop all earlier WACC processes and restart the
  server so it reloads the library files.
