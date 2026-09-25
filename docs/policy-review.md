# Framework alignment: commands and internals

Start with the [desktop guide](policy-review/README.md) for the normal workflow.
The desktop and CLI call the same local comparison service.

## Compare documents

```powershell
python -m wacc compare "C:\Policies\access.docx" "C:\Policies\recovery.pdf" --framework wa-csp --also-assess ism --also-assess aescsf --scope "Head office policies" --assessment comparison.wacc --format json
python -m wacc compare "C:\Policies\department.zip" --framework ism --scope "Department policy collection" --assessment department.wacc --format json
python -m wacc requirements comparison.wacc --status "Mentioned" --format json
python -m wacc gaps comparison.wacc --format json
python -m wacc evidence comparison.wacc --requirement wa-csp:3.2a --format json
python -m wacc report comparison.wacc --framework wa-csp --framework ism --format html --output alignment.html
```

`--framework` selects the first framework; repeat `--also-assess` for additional
ones. Reports can select any subset of frameworks already in the saved file.
CSV, Markdown and JSON reports are also supported. `--summary-only` removes
policy passage excerpts from reports. `--force` permits replacing an existing
report; reports cannot replace the saved comparison or any source file.

`compare` is the primary command. The older `analyse` command and review-history
commands remain available for existing integrations. They do not drive the new
desktop or alignment reports. `requirements`, `gaps` and `evidence` now return
alignment results. Scripts consuming their old review-oriented payloads need
updating. The public JSON contracts are in `schemas/policy/`.

Exit codes: **0** complete, **2** invalid arguments, **3** unusable input,
**4** unexpected failure, **5** corpus error, **6** output error,
**7** completed with document-reading limitations, **130** cancelled.
The legacy `analyse` command retains its pilot exit code of 7.

## What matching does

The versioned `policy-topics-1` method indexes policy sentences once and searches
every selected requirement. It uses the shared corpus spelling and stemming
functions and a small list of technical acronyms, such as MFA. Framework wording
and its parent context form each query. Generic words such as “security” and
“policy” cannot establish a match on their own.

A match normally needs at least three meaningful shared terms, or both terms of
a two-term requirement. Shared terms must represent at least 35% of the weighted
query. At 65%, clear wording about the requirement itself is labelled **Mentioned**.
Parent context alone cannot produce that result. Weights favour terms that
occur in fewer requirements in the same framework, so selecting another framework
does not change an existing framework's results. Lower-scoring matches, named framework
references, negative wording and qualifications are **Related wording**.
A result is about topic alignment, not full semantic agreement or compliance.

The search does not combine unrelated sentences or transfer results through
framework mappings. It records exact passage text, offsets, source hashes and
locations. Each excerpt is a source window of up to 1,600 characters, with offsets
into the retained passage. Highlight offsets are relative to that excerpt.
The five clearest distinct passages are shown, together with the total
number found. No matching passage produces **Not mentioned** only when all
included documents were fully read. Otherwise the result is **Unable to check**.
Unusual paraphrases can be missed; independently labelled real policy collections
are still needed to measure retrieval accuracy beyond the synthetic regression tests.

## Files and ZIPs

Multiple individual files and ZIP archives may be mixed in one comparison.
Supported members are `.pdf`, `.docx`, `.txt` and `.md`, including subfolders.
Unsupported entries and nested ZIPs are listed as skipped. Identical documents
are deduplicated by their content hash, including duplicates across archives.

ZIP contents are read in memory; no member path is written onto the computer.
Each document is parsed in a disposable worker with the existing Windows memory,
process and time limits. Source provenance retains the archive path, archive hash,
member name and document hash. Opening an original archived document opens its
archive after checking the archive hash.

| Limit | Maximum |
|---|---|
| Individual file or outer ZIP | 16 MiB |
| Total uncompressed contents of one ZIP | 32 MiB |
| Compression ratio per member | 200:1 |
| Entries in one ZIP | 2,048 |
| Supported documents across all inputs | 250 |
| Extracted text per document / comparison | 2 million / 8 million characters |
| Matching sentence windows | 50,000 |
| Parser duration / Windows worker memory | 30 seconds / 256 MiB |

Traversal, absolute paths, links, encrypted members, duplicate archive names and
excessive expansion are rejected. Scanned or partly unreadable PDFs are labelled
as incomplete. Cancellation or failed imports do not replace earlier saved runs.

## Framework updates

```powershell
python -m wacc corpus update --format json
python -m wacc corpus update --framework ism --format json
python -m wacc corpus update --framework aescsf --import-file "C:\Downloads\aescsf-core.xlsx" --format json
python -m wacc frameworks --format json
```

Updates discover the 2024 WA policy on its publication page, AESCSF Core on AEMO's
resources page, and ISM on ASD's official OSCAL mirror. Downloads use approved
HTTPS hosts, then parse and validate files before switching the active version.
Older copies remain available; failed downloads preserve the existing version.
A reduction of more than 20% in requirements is rejected for investigation.
Downloaded files supply source text and published links, never executable rules.

The cache is `%LOCALAPPDATA%\WACC\frameworks`; `WACC_FRAMEWORK_CACHE` can choose
another local directory. `WACC_LIBRARY` can point to a prepared repository.
`--corpus-version 2026.09.23-pilot.2` selects the original prepared local baseline.
Publisher text remains excluded from Git and from the application package.

## Saved comparisons and compatibility

`.wacc` files are local SQLite snapshots containing source text, framework
versions, matches and history. A canonical hash includes the alignment results;
validation checks every match against its recorded passage and source.
No database migration or destructive conversion is needed for old assessment files.

New files retain all extracted text by default. The CLI's `--retention evidence`
option retains matching passages and the saved search outcome. Old files without
alignment results can be compared against their retained text; missing retained
text prevents an unqualified “Not mentioned” result. Re-run with the originals
when a complete comparison is needed. Legacy review events remain stored but do
not change topic matches.

The app uses no AI inference or network requests during comparison or export.
Network access is limited to explicit framework acquisition/update commands.

## Development

Install `requirements-policy-dev.txt` for tests and builds. The runtime dependency
file excludes schema validators and packaging tools. See [tests](../tests/README.md)
and [optimisation notes](OPTIMISATION.md) for validation and performance measurement.
