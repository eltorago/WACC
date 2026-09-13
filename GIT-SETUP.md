# Putting this folder under git

The repository is this `tool` folder. The publisher source documents live in the folder
above it and stay out of it — half of them may not be redistributed, and a repository is
a way of redistributing something.

## Once

Double-click `git-init.cmd`, or run it from a prompt in this folder. It initialises the
repository, stages everything the rules allow, and makes the first commit.

If git stops and says it does not know who you are, set your identity once and run it
again:

```
git config --global user.name "Aidan"
git config --global user.email "you@example.com"
```

I cannot do this step for you. The bridge that writes files to this machine refuses to
write inside a `.git` directory, which is the right rule — a tool that can rewrite your
history from somewhere else is a tool that can quietly lose it.

## Taking changes from a session as commits

After that first commit, changes arrive as patch files in `patches\` rather than as
overwritten files, so the history and the reasons come with them:

```
git am patches\*.patch
del patches\*.patch
```

`git am` applies each one and commits it with the message it carries. If a patch will not
apply because you have edited the same lines, `git am --abort` puts everything back and
nothing is lost.

Loose files are still the fallback when a session cannot produce a patch. In that case
git will show them as modifications and you commit them yourself.

## What is tracked, and what is not

`.gitignore` is **generated** from `wacc/packaging.py`, not written by hand. What may be
committed and what may ship are one question, and answering it in two places is how the
two drift apart. After changing a licence or adding a framework:

```
python -m wacc.packaging --gitignore
```

A case in `tests/test_packaging.py` fails if the file on disk stops matching the rules,
so this cannot be forgotten quietly.

Four things stay out, for three different reasons.

| Not tracked | Why |
|---|---|
| `data/raw/`, and every `.pdf` `.docx` `.xlsx` anywhere | a publisher's own file is the publisher's, whatever its licence |
| `data/corpus/wa-csp.json`, `wa-circular.json`, `aescsf.json`, `cis-controls.json` | this tool wrote the JSON and every sentence in it is the publisher's; no licence has been read off the source |
| `data/corpus/detail/`, `data/review/` | CIS benchmark text, and unchecked extracts that nothing loads |
| `__pycache__/`, `*.pyc` | noise |

Two of those are already in your working copy and will keep working — git leaves
untracked files alone. They will not be in a clone, and a clone will say so under
**NOT IN THIS BUILD** rather than reporting those publishers as silent.

## Afterwards

```
git status
git add -A && git commit -m "what changed and why"
git log --oneline
```

There is no remote and I would leave it that way unless you have somewhere private to
push. The ignore rules mean a push would not carry anything unlicensed, but the corpus
extracts that *are* tracked still quote NIST, CISA, the OAG and the Commonwealth, and
each of those ships on terms this tool records rather than assumes.
