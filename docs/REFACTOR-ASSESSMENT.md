# Repository assessment — 23 September 2026

## Baseline inspected

The starting revision was `850b5cb`. The working tree was clean. No `AGENTS.md`
instructions were found in the repository. WACC was a Python 3.9+ standard-library
application, launched by `python -m wacc`, with a hand-rendered HTML interface and
a loopback `ThreadingHTTPServer`. It had no installer or standalone executable.

The control library, source acquisition and GRC/technical assessment instructions
are useful working features. Existing assessment imports and Sentinel workflows
were removed previously. This refactor introduces **policy-document coverage**;
it does not restore those operational/self-assessment import workflows.

The baseline suite returned **528 passed, 2 failed**, plus 19 historical plan
corrections. Both failures were intermittent Windows HTTP connection errors while
rejecting retired POST routes. The preceding audit had recorded the same symptom.
The refactor consumes bounded rejected request bodies before returning 404.

## Components and treatment

| Existing component | Treatment |
|---|---|
| Framework registry, source manifests, source edition metadata | Retain; adapt into pinned requirement snapshots. |
| WA policy extract and authoritative identifiers | Retain as local input. Use its 86 requirement records, not 109 containers plus records as the denominator. |
| Existing control workspace and technical tests | Preserve through `serve`; separate from policy coverage results. |
| Topic search, crosswalk and derived guidance | Preserve in the library. Do not treat topical matches as evidence of policy coverage. |
| DOCX/XML reader | Reuse format knowledge; introduce a bounded input boundary for untrusted policies. Existing publisher loaders are unchanged. |
| PDF preparation scripts | Retain for authoring. Policy import uses a pinned, bundled pypdf parser in a worker. |
| HTML/CSV exports | Retain for the library. New assessment exports share a report model with the desktop/CLI. |
| JSON/CSV corpus data | Preserve. No automatic conversion to approved deterministic rules. |
| Private `data/local` and custom source folders | Preserve. No scanning or migration of private assessment records. |

## Runtime inventory

There is no production LLM, embedding, trained-model, telemetry, CDN, or online
licence-check dependency in the inspected application. Network-capable source
acquisition exists in `wacc/sources.py` and the legacy Sources screen. It obtains
publisher files listed in `sources/acquisition.json`; it does not upload policies.
Publisher links in library pages can open the user's browser on explicit action.

The new `wacc.policy` analysis path performs no HTTP requests. Its desktop uses
Tk/Ttk, not an HTTP listener. It starts one disposable parser child at a time.
The child uses the same installed executable in a frozen build, or the current
Python interpreter in a source checkout. SQLite is embedded, with no database
server. The installed payload includes CPython, Tcl/Tk, SQLite and cryptography's
native dependency; these need application-control inventory and approval.

The legacy web interface remains a separately selected development/reference
interface. Its `serve` and `sources` commands are absent from the offline EXE
entry point. This does not certify the older server as the hardened desktop.

## Migration and release constraints

New `.wacc` files use application schema 1. Older unknown SQLite/JSON formats are
rejected, not rewritten. Existing private JSON/XLSX assessment material is untouched.
There is no known earlier `.wacc` schema to migrate. A converter requires an actual
schema fixture, must migrate a copy and must retain its original methodology.
Snapshots use SQLite backup; new analyses append runs and retain reviewer history.

Existing custom frameworks remain usable in the control library. Direct policy
evaluation requires explicit rule authoring, source review and a signed data-only
package. A mapping alone does not enable direct target coverage.

The host has Python 3.13, Tcl/Tk 8.6.15 and a .NET 6 runtime but **no .NET SDK**.
Tk permits a runnable native migration without reimplementing existing Python
loaders. See [the architecture decision](adr/001-offline-policy-review.md).

The WA CSP text is local import-only material. It is not added to Git or the
portable build. The current pilot checks one draft training-rule family against
WA CSP 3.2a; the source wording was compared with PDF page 15. This developer
comparison is not independent human approval. All other baseline requirements
remain manual review. Production signing, independent rule review, a permissioned
real-policy benchmark, accessibility acceptance and agency deployment testing
remain release gates.
