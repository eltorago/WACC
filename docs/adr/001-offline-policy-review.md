# ADR-001: Preserve Python and add native offline policy review

> Historical pilot design. The current workflow compares framework alignment and
> unmentioned requirements; see the [desktop guide](../policy-review/README.md).

**Status:** Accepted for engineering pilot; production desktop acceptance pending

**Date:** 23 September 2026

**Deciders:** Implementation decision under the supplied refactoring brief;
agency deployment and accessibility owners retain release approval.

## Context

The existing Python corpus and control library work and have extensive tests.
The brief permits repository-led choices and requires a runnable vertical slice.
This host has no .NET SDK and no current Windows Desktop runtime. Rewriting the
engine in C# now would duplicate working loaders before proving evidence semantics.

## Decision

Use `wacc.policy` as an independent Python application layer. Tk/Ttk supplies a
native desktop adapter; CLI and desktop call the same services. Keep the earlier
web library available separately. The offline executable has no server command.

Use SQLite with an application-owned schema, immutable run JSON snapshots and
append-only review events. JSON is stored inside a transaction rather than split
into dozens of premature tables. Schema validation, bounded reads and source
hashes preserve the contracts. This is a local single-user store, not a shared
database or tamper-proof audit ledger.

Use standard-library XML/ZIP parsing for bounded DOCX, UTF-8 TXT/Markdown and
pypdf 6.10.0 for text PDFs. Parsing runs in a separate process with a time limit.
A Windows Job Object limits worker memory to 256 MiB, disallows worker child
processes and terminates it when the parent closes the job. This is not a full
security sandbox; network/filesystem isolation and parser stress acceptance remain
deployment work.

Use a PyInstaller folder build for the engineering pilot. Bundle the interpreter
and runtime files, with no single-file runtime unpacking. Defer managed installer
selection and signing until an agency deployment owner and signing identity exist.
Do not represent this unsigned folder as a tested MSIX/MSI release.

## Options considered

| Option | Reuse / complexity | Runtime consequences |
|---|---|---|
| Python + Tk/Ttk | High reuse; one engine | CPython/Tcl/Tk payload; accessibility needs independent testing. Selected for pilot. |
| C# WPF + shared engine boundary | New UI and interop/build tooling | Requires supported .NET SDK/runtime and a separate servicing decision. Revisit after pilot. |
| WebView2 or Electron host | Could reuse HTML | Adds browser runtime distribution, servicing and bridge validation. Not selected. |
| Keep only the loopback web UI | Lowest UI effort | Retains listener and local request security surface. Not the offline assessment destination. |

## Consequences

Assessment semantics can be tested now without replacing the control library.
The CLI remains the stable boundary if a WPF interface later replaces Tk.
CPython, Tcl/Tk, SQLite, native crypto and the parser worker all need inventoried
trust decisions. Tk screen-reader and high-DPI acceptance are not assumed.

The pilot corpus is explicitly unapproved. Trusted corpus keys are empty by
default; no production signature is fabricated. The package verifier uses
Ed25519 from cryptography and an installation-owned trust store.

## References

- [Python Tkinter documentation](https://docs.python.org/3/library/tkinter.html)
- [SQLite backup API](https://www.sqlite.org/backup.html)
- [PyInstaller folder deployment](https://pyinstaller.org/en/stable/operating-mode.html)

## Follow-up gates

The subsequent source-update request adds an explicit online preparation action.
Only that action contacts configured publisher hosts; analysis, saved review and
exports remain offline. Raw publisher imports are versioned local data, separate
from signed rule packages. No source download can introduce rules or trusted keys.

- Independently approve obligation interpretations and evaluate a real-policy benchmark.
- Test native accessibility and decide whether Tk meets the target estate's requirements.
- Stress-test the implemented Windows Job Object limits on representative endpoints.
- Choose, sign and test the managed installer with agency application-control policies.
