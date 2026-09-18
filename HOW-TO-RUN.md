# Running WACC locally

WACC runs with Python 3.9 or later and the Python standard library. There is no package
installation step. Publisher files are acquired separately and kept out of the repository.

## Acquire source files

From the repository folder, run:

```powershell
python -m wacc sources
```

WACC downloads files available from publisher websites, verifies their reviewed content
and stores them in the ignored `sources/files/` cache. It prints instructions for sources
that require a sign-in, an interactive export or a user-supplied edition. Use
`python -m wacc sources --list` to review every acquisition method without downloading.

You can also start the app first and open **Sources**. Select **Download missing public
sources and reload** to acquire available documents and rebuild the live corpus without
restarting the server. The page reports progress and any remaining manual steps.

If you already downloaded documents, WACC can recognise and copy them automatically:

```powershell
python -m wacc sources --import-from "C:\path\to\downloads"
python -m wacc sources --status
```

Replace the example folder with your download folder. Files must match the reviewed
edition, but their filenames can differ. Originals and unmatched files are left alone.
The status command checks local files without downloading. It returns a non-zero exit
code when files are missing or changed, so setup scripts can detect incomplete acquisition.

## Start the web application

Open PowerShell in the repository folder and run:

```powershell
python -m wacc serve
```

When the terminal reports that WACC is ready, open the address it prints, normally
[http://127.0.0.1:8765/](http://127.0.0.1:8765/). If that port is occupied, WACC tries the
next available port. Keep the PowerShell window open while you use the application.
Press `Ctrl+C` in that window to stop it.

The server binds to `127.0.0.1`, so it is visible only on the computer where it is running.

In the Control workspace, select **GRC** or **Technical** beneath **Assess this
control**. The Technical view contains individual checks, artefacts, collection examples
and expected results. WACC displays the assessment instructions; it does not run commands
against your systems. **Framework coverage & checks** lists the new frameworks and offers
direct links to every technical check.

## Use a different source folder

To use a separate local collection instead, point `WACC_SOURCES` to that folder before
starting WACC:

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
| `sources` | Downloads public publisher files and explains manual acquisition. |
| `layout` | Shows the calculated source-browser layout at supported widths. |

Run `python -m wacc` to see the full command help.

## Run the checks

```powershell
$env:PYTHONUTF8 = '1'
python tests\run_all.py
python tools/revalidate_corpus.py
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
- **A framework is reported as unavailable** — run `python -m wacc sources`, follow any
  manual instructions, or confirm `WACC_SOURCES` points to the required publisher files.
- **Port 8765 is already in use** — open the address printed by the new instance. WACC
  checks up to 20 consecutive ports. You can also choose a starting port with
  `python -m wacc serve --port 8766`.
- **The page shows older controls** — stop all earlier WACC processes and restart the
  server so it reloads the library files.
- **New frameworks are missing from results** — check their source files were acquired,
  then enable them in Framework scope. Bookmarked URLs retain their previous selection.
