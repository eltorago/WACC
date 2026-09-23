# Engineering pilot deployment

## Build and launch

`python tools/build_policy.py` creates an **unsigned Windows x64 folder build** at
`data/local/offline-build/dist/wacc/`. Keep its entire directory together; the EXE
depends on `_internal`. The build bundles Python, Tcl/Tk, SQLite, pypdf and crypto.
End users do not install Python to run that folder, subject to agency approval.

Publisher files are not packaged. Users can open the desktop's **Framework updates**
page to acquire current sources, then work offline. AEMO may require manual download
and import. To reuse an existing prepared repository instead, set `WACC_LIBRARY`:

```powershell
$env:WACC_LIBRARY = 'C:\path\to\WACC'
& '.\data\local\offline-build\dist\wacc\wacc.exe' open
```

Double-clicking `wacc.exe` also opens the desktop. Saved `.wacc` files contain
snapshots and can be reopened without the source repository. Downloads happen
only through the explicit update action. Do not distribute locally imported
publisher text merely because an assessment contains it.

## Files and processes

| Location / process | Purpose |
|---|---|
| Approved application directory | Executable, bundled runtime, trust metadata; read-only for normal users in a managed installation. |
| User-selected `.wacc` | Unencrypted assessment snapshots, evidence and review history. |
| Adjacent `.lock` and SQLite journal | Short-lived write coordination and transactional recovery. |
| Adjacent uniquely named `.tmp` | Atomic new-file/report/snapshot staging. |
| `.backup-<id>` | Preserved prior snapshot when explicit replacement is requested. |
| User-selected report files | HTML, JSON, CSV or Markdown, with the selected evidence disclosure. |
| `%LOCALAPPDATA%\WACC\corpus` | Explicitly installed, verified versioned corpus packages. |
| `%LOCALAPPDATA%\WACC\frameworks` | Publisher source files, extracted requirements, version history and current-version index. Override with `WACC_FRAMEWORK_CACHE`. |
| Main `wacc.exe` | CLI or native desktop; no required listener or service. |
| One `wacc.exe --extract-worker` child | Disposable document parser; stdin carries the path, stdout carries structured extraction. |

Normal launch does not elevate, change execution policy, register services/tasks,
alter a firewall or trust store, install dependencies or create file associations.
Framework updates contact the allowlisted WA/AEMO publisher hosts or ASD's GitHub
mirror. Analysis, saved review and exports do not make these requests.
Opening originals invokes the registered application only on a deliberate click.
Paths can appear in host process logging; policy text is not put in command-line
arguments or diagnostic output. Deletion does not claim secure erasure.

## Trust and release artefacts

The build emits `release-manifest.json`, `SHA256SUMS.txt` and `sbom.cdx.json` next
to the `dist` folder. The manifest inventories every payload file and hash. It
labels the build unsigned; it does not invent signer metadata. The current SBOM
lists direct application dependencies and needs reconciliation with the full native
runtime inventory for a production release.

Production release is blocked on:

- Approved binary/corpus signing identity and administrator-managed trust roots.
- A chosen and tested managed installer, including upgrade/uninstall and file association.
- Narrow agency application-control trust decisions for all executable dependencies.
- Representative parser stress tests and measured application network activity.
  A 256 MiB, one-process Windows Job Object and a 30-second timeout are already implemented.
- Human-reviewed rule content, permitted baseline distribution and held-out real-policy evaluation.
- Accessibility, screen-reader, high-DPI and keyboard acceptance on the target Windows estate.
- Clean standard-user offline installation and enforced App Control/AppLocker tests.

Only the development Windows host and the tests recorded in the implementation
report have been exercised. A successful EXE run on this machine is not a managed
endpoint deployment test. No recommendation to disable host security is part of
this package.
