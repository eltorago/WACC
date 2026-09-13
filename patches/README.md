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

This folder is normally empty. It is tracked so that it exists.
