"""Check that releases include only reviewed publisher material.

The tests cover the real repository and small fixtures for exclusion rules that are not
triggered by the current checkout.
"""

import os
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.build import build  # noqa: E402
from wacc.model import Licence  # noqa: E402
from wacc.packaging import (  # noqa: E402
    EXCLUDED_DIRECTORIES,
    SOURCE_SUFFIXES,
    check,
    excluded_but_present,
    import_only_sources,
    would_ship,
    approved_sources,
)
from wacc.registry import DETAIL_SOURCES, FRAMEWORKS  # noqa: E402
from wacc.search import SearchIndex  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def temporary_tree(label):
    """Return a writable, unique fixture path within the repository."""
    path = os.path.join(ROOT, ".wacc-%s-test-%s" % (label, uuid.uuid4().hex))
    os.makedirs(path)
    return path


class Check:
    def __init__(self) -> None:
        self.failed = 0

    def expect(self, condition, area, detail, why=""):
        if condition:
            print("  pass  %-11s %s" % (area, detail))
        else:
            self.failed += 1
            print("  FAIL  %-11s %s" % (area, detail))
            if why:
                print("        from: %s" % why)


def run() -> int:
    check_ = Check()
    shipping = would_ship(ROOT)
    violations = check(ROOT)
    caught = excluded_but_present(ROOT)

    # -- nothing forbidden ships -------------------------------------------

    check_.expect(
        not violations,
        "ship", "the shipping set holds no forbidden file (%d files)" % len(shipping),
        "; ".join(v.describe() for v in violations[:3]),
    )
    check_.expect(
        not any(p.startswith(os.path.join("sources", "files")) for p in shipping),
        "ship", "no publisher source file ships",
        "publisher files belong in the ignored local source cache",
    )
    check_.expect(
        not any(p.startswith(os.path.join("data", "raw")) for p in shipping),
        "ship", "nothing under data/raw ships",
    )
    check_.expect(
        not any(
            p.startswith(os.path.join("data", "corpus", "detail")) for p in shipping
        ),
        "ship", "no CIS benchmark text ships",
        "CIS terms restrict redistribution and the benchmarks are import-only",
    )
    forbidden = import_only_sources()
    check_.expect(
        not any(os.path.basename(p) in forbidden for p in shipping),
        "ship", "no extract of import-only publisher text ships",
        "data/corpus/wa-csp.json is JSON this tool wrote and every sentence in it is the "
        "WA Government's",
    )
    # The cases above ask packaging which files are forbidden, which is the rule under
    # test: if import_only_sources ever returns nothing they all pass and the tree
    # ships the lot. These two read the answer off the registry and off a written list
    # instead, so the rule cannot clear itself.
    from_registry = {
        "%s.json" % f.key for f in FRAMEWORKS if f.licence is not Licence.SHIPPABLE
    }
    from_registry.update("%s.json" % s["key"] for s in DETAIL_SOURCES)
    check_.expect(
        bool(from_registry)
        and not any(os.path.basename(p) in from_registry for p in shipping),
        "ship", "the registry's own import-only list (%d files) is absent from the "
        "shipping set" % len(from_registry),
        "asking packaging what is forbidden and then asking whether any of it ships is "
        "one question, not two",
    )
    named = ("wa-csp.json", "wa-circular.json", "aescsf.json", "cis-controls.json")
    check_.expect(
        not any(os.path.basename(p) in named for p in shipping),
        "ship", "the four extracts known to be import-only are named and absent",
        "a list computed from the thing being tested is not independent of it",
    )

    # -- every registry input can be acquired ------------------------------

    from wacc.sources import load_catalogue
    permission_entries, acquisition_entries = load_catalogue()
    named = [
        (framework.key, name)
        for framework in FRAMEWORKS
        for name in framework.all_source_files()
    ]
    absent = [
        (key, name) for key, name in named
        if name not in permission_entries or name not in acquisition_entries
    ]
    check_.expect(
        bool(named) and not absent,
        "registry", "every framework source has permission and acquisition records "
        "(%d checked)" % len(named),
        "missing: %s" % ", ".join("%s -> %s" % pair for pair in absent[:3]),
    )

    # -- the rules are doing work ------------------------------------------

    kinds = {rule for _, rule in caught}
    check_.expect(
        bool(caught),
        "not vacuous", "the rules excluded %d files that are present in the tree"
        % len(caught),
        "a packaging check that passes because there is nothing left to catch has "
        "stopped checking",
    )
    check_.expect(
        "import-only publisher text" in kinds,
        "not vacuous", "the import-only rule caught something",
    )
    check_.expect(
        any(
            os.path.basename(p) in ("wa-csp.json", "wa-circular.json")
            for p, _ in caught
        ),
        "not vacuous", "the WA extracts specifically are excluded",
        "they are the most WA-relevant corpora in the tool and the ones a fresh install "
        "will not have, which is a fact worth failing loudly about rather than losing",
    )

    # Exercise rules that the clean repository does not trigger with a purpose-built
    # tree. This keeps the test meaningful without retaining obsolete raw fixtures.
    staging = temporary_tree("packaging")
    try:
        os.makedirs(os.path.join(staging, "wacc"))
        os.makedirs(os.path.join(staging, "data", "raw"))
        open(os.path.join(staging, "wacc", "model.py"), "w").close()
        open(os.path.join(staging, "a-publisher-standard.pdf"), "w").close()
        open(os.path.join(staging, "wacc", "workbook.xlsx"), "w").close()
        open(os.path.join(staging, "data", "raw", "private-source.pdf"), "w").close()
        staged = would_ship(staging)
        check_.expect(
            staged == [os.path.join("wacc", "model.py")],
            "suffix rule", "a source document outside data/raw is still excluded",
            "the directory rule reaches every one of them in this tree, so the suffix "
            "rule is never the thing that catches anything and would rot unnoticed",
        )
        check_.expect(
            not check(staging),
            "suffix rule", "and the check agrees the staged tree is clean",
        )
        staged_caught = excluded_but_present(staging)
        check_.expect(
            any(rule == "excluded directory" for _, rule in staged_caught),
            "directory rule", "an excluded development directory is caught",
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # -- what ships has to run ----------------------------------------------
    #
    # Copy only the calculated shipping set and run a real query from that copy. This
    # catches missing application files and confirms that intentionally excluded corpus
    # extracts are reported as unavailable.
    shipped = temporary_tree("shipping")
    try:
        for relative in shipping:
            destination = os.path.join(shipped, relative)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, relative), destination)
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["WACC_SOURCES"] = os.path.join(shipped, "sources", "files")
        run = subprocess.run(
            [sys.executable, "-m", "wacc", "search", "multi-factor authentication"],
            capture_output=True, text=True, cwd=shipped, env=environment, timeout=300,
        )
        check_.expect(
            run.returncode == 0 and "multi-factor authentication" in run.stdout.lower(),
            "runs", "the shipping set alone answers a query (%d files)" % len(shipping),
            "stderr: %s" % (run.stderr or "")[-200:],
        )
        check_.expect(
            "NOT IN THIS BUILD" in run.stdout,
            "runs", "a shipped build says which frameworks it does not hold",
            "an unavailable framework must not look like a publisher with no matching controls",
        )
        check_.expect(
            "WA CSP" in run.stdout.split("NOT IN THIS BUILD")[-1]
            if "NOT IN THIS BUILD" in run.stdout else False,
            "runs", "an excluded framework extract is named as unavailable",
            "the source PDF may be included while its generated text remains import-only",
        )
    finally:
        shutil.rmtree(shipped, ignore_errors=True)

    # -- attribution ships with the text that requires it ------------------

    requiring = [f for f in FRAMEWORKS if f.attribution]
    check_.expect(
        bool(requiring),
        "attribution", "%d framework states an acknowledgement it requires"
        % len(requiring),
    )
    for framework in requiring:
        check_.expect(
            framework.licence is Licence.SHIPPABLE or
            (framework.key == 'scf' and framework.licence is Licence.IMPORT_ONLY and 'CC BY-ND' in framework.attribution),
            "attribution", "%s states attribution with a reviewed distribution policy" % framework.key,
            "SCF attribution must remain visible for local use while adapted material remains excluded from distribution",
        )

    corpus, _ = build(verbose=False)
    index = SearchIndex(corpus)
    from wacc.analysis import analyse, gather
    from wacc.render import export, html, text

    subject = "multi-factor authentication"
    payload = analyse(
        corpus, subject, gather(corpus, index, subject),
        display=[h.control for h in index.search(subject, limit=25).hits],
    )
    named = {name for name, _ in payload.attributions}
    check_.expect(
        "OAG WA" in named,
        "attribution", "a result holding OAG text carries the OAG acknowledgement",
        "the OAG's copyright page grants reproduction provided the source is "
        "acknowledged, so shipping the text without it is the same breach as shipping "
        "it with no grant",
    )
    rendered = {
        "terminal": text.render(corpus, payload),
        "csv": export.to_csv(corpus, payload),
        "markdown": export.to_markdown(corpus, payload),
        "html": html.render(corpus, payload),
    }
    for name, body in rendered.items():
        check_.expect(
            "Office of the Auditor General" in body,
            "attribution", "the %s renderer carries the acknowledgement" % name,
        )

    empty = analyse(corpus, "stationery procurement", [], display=[])
    check_.expect(
        not empty.attributions,
        "attribution", "a result holding no OAG text carries no OAG acknowledgement",
        "an acknowledgement printed where the text is absent is noise, and it trains a "
        "reader to skip the line that matters",
    )

    # -- what may be committed is what may ship ------------------------------
    #
    # Two places answering one question is how the two drift apart. The .gitignore is
    # generated from these rules; this fails if it has been hand-edited or if a rule
    # changed and the file did not.
    from wacc.packaging import gitignore  # noqa: E402

    ignore_path = os.path.join(ROOT, ".gitignore")
    check_.expect(
        os.path.exists(ignore_path),
        "git", ".gitignore is present",
        "without it a commit can track the local publisher source cache",
    )
    if os.path.exists(ignore_path):
        with open(ignore_path, encoding="utf-8") as handle:
            on_disk = handle.read()
        check_.expect(
            on_disk == gitignore(),
            "git", ".gitignore still matches the shipping rules",
            "run python -m wacc.packaging --gitignore",
        )
        lines = {l.strip() for l in on_disk.splitlines() if l.strip()}
        missing_dirs = [
            d for d in EXCLUDED_DIRECTORIES
            if "/%s/" % d.replace(os.sep, "/") not in lines
        ]
        missing_names = [n for n in import_only_sources() if n not in lines]
        missing_suffixes = [s for s in SOURCE_SUFFIXES if "*%s" % s not in lines]
        check_.expect(
            not missing_dirs and not missing_names and not missing_suffixes,
            "git", "every excluded directory, suffix and import-only extract is ignored "
            "(%d names)" % len(import_only_sources()),
            "missing: %s" % (missing_dirs + missing_names + missing_suffixes)[:4],
        )
        check_.expect(
            bool(import_only_sources()) and "wa-csp.json" in lines,
            "git", "the WA extracts specifically cannot be committed",
            "they are the most WA-relevant corpora in the tool and the ones whose "
            "licence has not been read off a source document",
        )

    # -- the registry says what it means -----------------------------------

    for framework in FRAMEWORKS:
        if framework.licence is Licence.SHIPPABLE:
            continue
        check_.expect(
            any(
                word in note.lower()
                for note in framework.notes
                for word in ("licen", "redistrib", "import only", "ship", "states none")
            ),
            "registry", "%s says why it is import-only" % framework.key,
            "an import-only marking with no reason is a guess nobody can check",
        )
    check_.expect(
        all(str(s["key"]) + ".json" in import_only_sources() for s in DETAIL_SOURCES),
        "registry", "every benchmark source is treated as import-only",
    )

    print("\npackaging: %d failed" % check_.failed)
    return 1 if check_.failed else 0


if __name__ == "__main__":
    sys.exit(run())
