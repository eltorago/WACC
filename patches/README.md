# patches

Changes from a working session land here as `.patch` files, numbered in the order they
should be applied.

```
git am patches\*.patch
del patches\*.patch
```

Each patch carries its own commit message, so the history says what changed and why
rather than recording one undifferentiated import. `git am --abort` backs the whole thing
out if one will not apply.

## MANIFEST.json

Written beside the patches. For each one it records the SHA-256 of every file that patch
leaves behind, and of every file as it was before, so a session can tell whether a patch
has been applied without reading your repository — the bridge that writes files to this
machine refuses to touch a `.git` directory, and that is the right rule.

```
python tools\patch_status.py --check .
```

`applied`, `not applied`, or `EDITED SINCE` if the files match neither state. It will say
`cannot tell` rather than guess when it cannot read the files it needs.

Neither the patches nor the manifest are tracked in git. They are transport: a session
writes them, `git am` consumes them, and they are regenerable from the history they
carry. This file is tracked, so the folder exists in a clone.
