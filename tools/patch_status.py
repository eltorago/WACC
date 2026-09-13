"""Which patches a copy of this tool has had applied.

Extraction tooling. Not part of the shipped package.

A session cannot read the repository on the work machine — the device bridge refuses to
touch a `.git` directory, which is the right rule — so "has patch 0001 been applied" has
to be answered from the working files themselves rather than from git.

It is answered by content. Every patch records the SHA-256 of each file it leaves behind,
so a copy of the tool can be compared against those fingerprints and told apart: the files
match the state after that patch, they match the state before it, or they match neither
because someone has edited them. Nothing is inferred from a date or a file size.

    python tools/patch_status.py --record        after generating patches
    python tools/patch_status.py --check <dir>   against a copy of the tool
"""

import hashlib
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional, Sequence

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHES = os.path.join(HERE, "patches")
MANIFEST = os.path.join(PATCHES, "MANIFEST.json")
APPLIED = os.path.join(PATCHES, "APPLIED.json")


def _sha(path: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(
        ["git"] + list(args), cwd=HERE, capture_output=True, text=True,
        encoding="utf-8", check=True,
    ).stdout.strip()


def record() -> int:
    """Fingerprint every patch in patches/ from the commit it carries."""
    entries: List[Dict[str, object]] = []
    # git am and manual conflict resolution produce new commit IDs. An explicit map
    # records those IDs in application order; filename sorting is not a history.
    applied = {}
    if os.path.isfile(APPLIED):
        with open(APPLIED, encoding="utf-8") as handle:
            applied = json.load(handle)["integrated_commits"]
    names = list(applied) + [n for n in sorted(os.listdir(PATCHES)) if n not in applied]
    for name in names:
        if not name.endswith(".patch"):
            continue
        commit = ""
        subject = ""
        with open(os.path.join(PATCHES, name), encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("From ") and not commit:
                    commit = line.split()[1]
                elif line.startswith("Subject: "):
                    subject = line[len("Subject: "):].strip()
                    if subject.startswith("[PATCH"):
                        subject = subject.split("] ", 1)[-1]
                    break
        if not commit:
            continue
        original_commit = commit
        commit = applied.get(name, commit)
        try:
            commit = _git("rev-parse", "--verify", "%s^{commit}" % commit)
        except subprocess.CalledProcessError:
            print("Cannot record %s: commit is unavailable; existing manifest preserved."
                  % name)
            return 2
        touched = [
            p for p in _git("show", "--name-only", "--pretty=format:", commit).splitlines()
            if p.strip()
        ]
        if not touched:
            print("Cannot record %s: commit contains no changed file evidence." % name)
            return 2
        after = {}
        for path in touched:
            blob = subprocess.run(
                ["git", "show", "%s:%s" % (commit, path)],
                cwd=HERE, capture_output=True,
            )
            if blob.returncode == 0:
                after[path] = hashlib.sha256(blob.stdout).hexdigest()
        parent = _git("rev-parse", "%s^" % commit)
        before = {}
        for path in touched:
            blob = subprocess.run(
                ["git", "show", "%s:%s" % (parent, path)],
                cwd=HERE, capture_output=True,
            )
            before[path] = (
                hashlib.sha256(blob.stdout).hexdigest() if blob.returncode == 0 else None
            )
        entries.append(
            {
                "patch": name,
                "commit": commit,
                "original_commit": original_commit,
                "subject": subject,
                "files_after": after,
                "files_before": before,
            }
        )

    os.makedirs(PATCHES, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"patches": entries}, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print("recorded %d patch%s in %s"
          % (len(entries), "" if len(entries) == 1 else "es", MANIFEST))
    for entry in entries:
        print("   %-52s %d files" % (entry["patch"][:52], len(entry["files_after"])))
    return 0


def check(root: str) -> int:
    """How far through the series a copy of the tool has got.

    A patch series is linear, so the question is a depth rather than a set. Asking each
    patch on its own gets it wrong: tests/injected.py is touched by patch 1 and again by
    patch 2, so after both are applied it matches patch 2 and not patch 1, and patch 1
    reads as edited since. What a file should match is the newest patch at or below the
    depth being tested that touches it.
    """
    if not os.path.exists(MANIFEST):
        print("no manifest; run --record first")
        return 2
    with open(MANIFEST, encoding="utf-8") as handle:
        entries = json.load(handle)["patches"]
    if not entries or any(not e.get("files_after") for e in entries):
        print("Cannot determine patch status: manifest contains no file evidence.")
        return 2

    def state_at(depth: int) -> Dict[str, Optional[str]]:
        """The hash each touched file should have once patches 1..depth are applied."""
        wanted: Dict[str, Optional[str]] = {}
        for index, entry in enumerate(entries):
            source = entry["files_after"] if index < depth else entry["files_before"]
            for path_, digest in source.items():
                if index < depth or path_ not in wanted:
                    wanted[path_] = digest
        return wanted

    def mismatches(depth: int) -> List[str]:
        out = []
        for path_, digest in state_at(depth).items():
            actual = _sha(os.path.join(root, path_))
            if digest is None:
                # The patch creates this file, so before it the file should not be there.
                if actual is not None:
                    out.append(path_)
            elif actual is None or actual != digest:
                out.append(path_)
        return out

    depths = [d for d in range(len(entries) + 1) if not mismatches(d)]
    applied = max(depths) if depths else None

    print("patch status of %s\n" % root)
    print("%-52s %s" % ("patch", "state"))
    print("-" * 74)
    for index, entry in enumerate(entries):
        if applied is None:
            state = "cannot tell — this copy matches no point in the series"
        elif index < applied:
            state = "applied"
        else:
            state = "outstanding"
        print("%-52s %s" % (entry["patch"][:52], state))
        print("%-52s %s" % ("", entry["subject"][:70]))
    print("-" * 74)
    if applied is None:
        unreadable = mismatches(0)
        print("this copy matches neither the state before the series nor any point in "
              "it;\n%d file%s differ from what the manifest expects, first: %s"
              % (len(unreadable), "" if len(unreadable) == 1 else "s",
                 ", ".join(unreadable[:3])))
        return 1
    print("applied up to %d of %d; %d outstanding"
          % (applied, len(entries), len(entries) - applied))
    return 1 if applied < len(entries) else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--record" in argv:
        return record()
    if "--check" in argv:
        index = argv.index("--check")
        if index + 1 >= len(argv):
            print("--check needs a directory")
            return 2
        return check(argv[index + 1])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
