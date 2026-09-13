"""What may be shipped, decided by rule rather than by habit.

Licensing is a test. Half this corpus is publisher text that may not be redistributed —
the AESCSF practice text, CIS control and benchmark text, and every extract whose licence
has not yet been read off the source document's own copyright page. A build that quietly
includes one of those is a licence breach, and it will not announce itself.

So the rules live here, the test runs them over the real tree in the real test suite, and
a second test asserts that the tree still contains things the rules must exclude. A
packaging check that passes because there is nothing left to catch has stopped checking.

Source documents are excluded by default. The exact files reviewed in
sources/permissions.json may ship under sources/files/ with their original notices.
Generated extracts still follow the separate framework registry rules.
"""

import os
import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .model import Licence
from .registry import DETAIL_SOURCES, FRAMEWORKS

# Excluded unless the exact path is in the reviewed source manifest.
SOURCE_SUFFIXES = (".pdf", ".xlsx", ".xlsm", ".xls", ".docx", ".doc", ".zip", ".epub")


def approved_sources(root: str) -> Dict[str, Dict]:
    """Explicit source paths; no automatic approval of new names or editions."""
    manifest = os.path.join(root, "sources", "permissions.json")
    if not os.path.isfile(manifest):
        return {}
    with open(manifest, encoding="utf-8") as handle:
        entries = json.load(handle)["files"]
    approved = {}
    for entry in entries:
        name = entry["filename"]
        if not name or name in (".", "..") or any(c in name for c in "/\\\n\r*?[]"):
            raise ValueError("Unsafe source filename: %r" % name)
        if entry["status"] == "included":
            approved[os.path.join("sources", "files", name)] = entry
    return approved

# Never shipped whatever is in them.
EXCLUDED_DIRECTORIES = (
    os.path.join("data", "raw"),
    # CIS benchmark recommendations, audit steps and remediation text.
    os.path.join("data", "corpus", "detail"),
    # The sentence route's output, which nothing loads: unchecked extracts held for
    # reading, not corpus. Shipping them would put text nobody verified beside text
    # that was.
    os.path.join("data", "review"),
)

# Not licence questions, just noise that should not be in a package.
NOISE = ("__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".idea", ".vscode")
NOISE_SUFFIXES = (".pyc", ".pyo", ".log", ".tmp", ".swp")


@dataclass
class Violation:
    path: str
    rule: str
    why: str

    def describe(self) -> str:
        return "%s — %s (%s)" % (self.path, self.rule, self.why)


def import_only_sources() -> Dict[str, str]:
    """Every corpus file whose text belongs to a publisher who has not licensed it.

    Keyed by the generated file's name, because that is what a packager sees: the licence
    of data/corpus/wa-csp.json is not a property of the JSON, it is a property of the
    document the JSON was extracted from.
    """
    out: Dict[str, str] = {}
    for framework in FRAMEWORKS:
        if framework.licence is Licence.SHIPPABLE:
            continue
        out["%s.json" % framework.key] = (
            "%s is import-only: %s"
            % (framework.short_name, _reason(framework))
        )
    for source in DETAIL_SOURCES:
        out["%s.json" % source["key"]] = (
            "%s is CIS benchmark text, which is import-only" % source["key"]
        )
    return out


def _reason(framework) -> str:
    for note in framework.notes:
        lowered = note.lower()
        if any(word in lowered for word in ("licen", "redistrib", "import only", "ship")):
            return note
    return "the registry marks it import-only and no licence has been read from the source"


def would_ship(root: str) -> List[str]:
    """The files a package would contain, after the exclusion rules are applied."""
    kept: List[str] = []
    excluded = tuple(os.path.normpath(d) for d in EXCLUDED_DIRECTORIES)
    forbidden_names = import_only_sources()
    approved = approved_sources(root)

    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in NOISE]
        relative_dir = os.path.relpath(directory, root)
        normalised = os.path.normpath(relative_dir)
        if normalised != "." and any(
            normalised == d or normalised.startswith(d + os.sep) for d in excluded
        ):
            subdirectories[:] = []
            continue
        for name in files:
            path = os.path.normpath(os.path.join(relative_dir, name))
            if path.startswith(os.path.join("sources", "files") + os.sep):
                if path in approved:
                    kept.append(path)
                continue
            if name.endswith(NOISE_SUFFIXES):
                continue
            if name.lower().endswith(SOURCE_SUFFIXES):
                continue
            if name in forbidden_names:
                continue
            path = os.path.join(relative_dir, name) if normalised != "." else name
            kept.append(os.path.normpath(path))
    return sorted(kept)


def check(root: str) -> List[Violation]:
    """Anything in the shipping set that must not be there."""
    out: List[Violation] = []
    forbidden_names = import_only_sources()
    excluded = tuple(os.path.normpath(d) for d in EXCLUDED_DIRECTORIES)
    approved = approved_sources(root)

    for path, entry in approved.items():
        full = os.path.join(root, path)
        if not os.path.isfile(full):
            out.append(Violation(path, "missing approved source", "restore the reviewed file"))
        else:
            with open(full, "rb") as handle:
                digest = hashlib.sha256(handle.read()).hexdigest()
            if digest != entry["sha256"]:
                out.append(Violation(path, "unreviewed source bytes", "file differs from permission review"))

    for path in would_ship(root):
        name = os.path.basename(path)
        parent = os.path.dirname(path)
        if name.lower().endswith(SOURCE_SUFFIXES) and path not in approved:
            out.append(
                Violation(path, "publisher source document",
                          "publisher source has no reviewed permission entry")
            )
        if any(parent == d or parent.startswith(d + os.sep) for d in excluded):
            out.append(
                Violation(path, "excluded directory",
                          "%s is excluded in full" % parent)
            )
        if name in forbidden_names:
            out.append(
                Violation(path, "import-only publisher text", forbidden_names[name])
            )
    return out


def excluded_but_present(root: str) -> List[Tuple[str, str]]:
    """What the rules actually caught, so a passing check can be shown to be doing work.

    A packaging test that passes because the tree no longer contains a workbook has
    stopped testing anything. This reports the files the rules excluded, and the suite
    fails if that list is empty or missing a category.
    """
    caught: List[Tuple[str, str]] = []
    forbidden_names = import_only_sources()
    excluded = tuple(os.path.normpath(d) for d in EXCLUDED_DIRECTORIES)
    approved = approved_sources(root)

    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [d for d in subdirectories if d not in NOISE]
        relative_dir = os.path.relpath(directory, root)
        normalised = os.path.normpath(relative_dir)
        in_excluded_dir = normalised != "." and any(
            normalised == d or normalised.startswith(d + os.sep) for d in excluded
        )
        for name in files:
            path = os.path.normpath(
                os.path.join(relative_dir, name) if normalised != "." else name
            )
            if path in approved:
                continue
            if path.startswith(os.path.join("sources", "files") + os.sep):
                caught.append((path, "unreviewed source document"))
                continue
            if in_excluded_dir:
                caught.append((path, "excluded directory"))
            elif name.lower().endswith(SOURCE_SUFFIXES):
                caught.append((path, "publisher source document"))
            elif name in forbidden_names:
                caught.append((path, "import-only publisher text"))
    return caught


GITIGNORE_HEADER = """# Generated from wacc/packaging.py. Do not hand-edit.
#
# What may be committed is the same question as what may ship, and answering it in two
# places is how the two drift apart. `python -m wacc.packaging --gitignore` rewrites this
# file from the rules in that module, and a case in tests/test_packaging.py fails if the
# file on disk no longer matches them.
#
# Source documents are excluded by default. Only reviewed paths from
# sources/permissions.json are allowed under sources/files/; check() verifies hashes.
"""


def gitignore() -> str:
    """The .gitignore these rules imply, written out.

    Three kinds of entry and they are excluded for three different reasons. Noise is not
    a licence question. A source document is excluded for what it is. A generated extract
    is excluded for where its text came from — data/corpus/wa-csp.json is JSON this tool
    wrote and every sentence in it is the WA Government's.
    """
    lines = [GITIGNORE_HEADER, "# Noise"]
    lines.extend(sorted("%s/" % name for name in NOISE if name != ".git"))
    lines.extend(sorted("*%s" % suffix for suffix in NOISE_SUFFIXES))

    lines.append("")
    lines.append("# Excluded in full, whatever they hold")
    for directory in EXCLUDED_DIRECTORIES:
        lines.append("/%s/" % directory.replace(os.sep, "/"))

    lines.append("")
    lines.append("# Publisher files require an explicit reviewed exception")
    for suffix in sorted(SOURCE_SUFFIXES):
        lines.append("*%s" % suffix)
        lines.append("*%s" % suffix.upper())

    lines.append("")
    lines.append("# Extracts of publisher text that has not been licensed for reuse")
    for name in sorted(import_only_sources()):
        lines.append(name)

    lines.extend(["", "# Reviewed, unmodified source documents only", "/sources/files/*"])
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in sorted(approved_sources(root)):
        lines.append("!/%s" % path.replace(os.sep, "/"))

    return "\n".join(lines) + "\n"


def summary(root: str) -> str:
    shipping = would_ship(root)
    caught = excluded_but_present(root)
    kinds: Dict[str, int] = {}
    for _, rule in caught:
        kinds[rule] = kinds.get(rule, 0) + 1
    lines = [
        "would ship        %d files" % len(shipping),
        "excluded          %d files" % len(caught),
    ]
    for rule, count in sorted(kinds.items()):
        lines.append("  %-28s %d" % (rule, count))
    problems = check(root)
    lines.append("violations        %d" % len(problems))
    for violation in problems:
        lines.append("  %s" % violation.describe())
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--gitignore" in sys.argv:
        target = os.path.join(here, ".gitignore")
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(gitignore())
        print("wrote %s" % target)
    else:
        print(summary(here))
