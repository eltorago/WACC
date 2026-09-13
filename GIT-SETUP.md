# Git tracking and source permissions

This `tool` folder is the repository. Its private remote is
https://github.com/eltorago/WACC, with `main` tracking `origin/main`.

## Publisher sources

The [source permission review](sources/README.md) records which exact source files may
be included in this private, non-commercial project. Approved, unmodified files live
in `sources/files/`; their hashes and evidence are in `sources/permissions.json`.
Files without a suitable permission remain in the parent folder outside Git.

The owner confirmed solely non-commercial use on 13 September 2026. Review the source
terms before public redistribution or commercial use. Source-document permissions
do not assign a licence to WACC code.

`.gitignore` is generated from `wacc/packaging.py` and the permission manifest:

```
python -m wacc.packaging --gitignore
python -m wacc.packaging
python -m unittest discover -s tests -p test_source_permissions.py
```

The ignore rules allow only reviewed source paths. The packaging check verifies their
SHA-256 hashes, so a different edition requires another review. Do not bypass the
exclusions with `git add -f` without reviewing permission. `data/raw/`,
`data/corpus/detail/`, `data/review/` and import-only corpus extracts remain excluded.
Permission for an intact source does not automatically approve transformed extracts,
especially under a NoDerivatives licence.

## Saving changes

```
git status
git add <reviewed-files>
git commit -m "Describe the change"
git push
```

Existing session patches are preserved as files; tracking a patch does not apply it.
Review a patch before applying it and recheck source permissions if it changes
packaging rules or imports publisher text.
