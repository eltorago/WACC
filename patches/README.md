# Delivered patches

All four delivered patches have been integrated. See APPLIED.json for the actual local
commit IDs and application order. Original patch headers refer to commits in Claude's
source repository; git am produces different IDs here.

The GUI patch was already applied to the working files before the remaining series.
The source-text and Essential Eight patches applied cleanly. The patch-status change
was merged manually to preserve the reviewed source-file permissions.

```
python tools/patch_status.py --record
python tools/patch_status.py --check .
```

The tool uses APPLIED.json when present, then fingerprints the corresponding commits.
It refuses to overwrite the manifest if a required commit cannot be resolved. The
check compares file content, so later edits may legitimately report a mismatch.

Existing patch files and the manifest remain tracked as the delivery record. New patch
transport is ignored and omitted from packaged builds. Source permissions are recorded
separately in sources/permissions.json and are not affected by these transport rules.

Do not run git am over this directory again: the patches are already integrated.
