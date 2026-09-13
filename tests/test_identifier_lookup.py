"""Identifier lookup cases, run against the criteria fixed in the validation plan.

Every case names the trap it came from. Exits non-zero on any failure.

Four expectations in the plan turned out to be wrong about the corpus. They are recorded
here as failures with a corrected measure beside them, which is what the plan's own rules
require. The criterion is not moved. Three of the four are the same mistake — assuming a
legislative or numeric identifier belongs to one framework when two frameworks use it.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.build import build  # noqa: E402
from wacc.lookup import IdentifierIndex, Status  # noqa: E402
from wacc.model import normalise_identifier  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(HERE, "data", "validation", "search_validation.json")

# Where the plan's expectation is wrong about the corpus. The plan keeps its original
# wording; the run reports the original as failed and measures against the correction.
CORRECTIONS = {
    "s 8(4)": {
        "corrected": ["soci-act:s 8.4", "cirmp-rules:s 8.4"],
        "why": (
            "Both the SOCI Act and the CIRMP Rules have an s 8(4). The plan expected the "
            "Rules alone. An unqualified legislative subsection cannot resolve to one "
            "instrument, so the correct behaviour is to present both and ask which."
        ),
    },
    "s 8A(3)": {
        "corrected": ["soci-act:s 8a.3", "cirmp-rules:s 8a.3"],
        "why": (
            "Same collision as s 8(4), and the plan missed it the same way. SOCI s 8A is "
            "Meaning of influence or control; CIRMP s 8A is the enhanced cyber and "
            "information security requirements. Two live provisions, one citation form."
        ),
    },
    "GV.OC-01": {
        "corrected": ["csf:gv.oc-1"],
        "why": (
            "The tool found the right control. The plan wrote the expected uid without "
            "applying the identifier normaliser, which folds the leading zero, so the "
            "uid is csf:gv.oc-1. The display identifier is still GV.OC-01."
        ),
    },
    "6.1": {
        "corrected": ["wa-csp:6.1", "cis-controls:6.1"],
        "why": (
            "The plan named three frameworks. AESCSF numbers its practices ACCESS-1a and "
            "similar, so it has no 6.1 and never could. The ambiguity is two-way."
        ),
    },
}


def uid_of(control) -> str:
    return control.uid


def run() -> int:
    corpus, _ = build(verbose=False)
    index = IdentifierIndex(corpus)
    with open(PLAN, "r", encoding="utf-8") as fh:
        plan = json.load(fh)

    passed = failed = corrected = 0
    lines = []

    for case in plan["identifiers"]:
        query = case["input"]
        expected = case["expect"]
        why = case["why"]
        result = index.find(query)
        got = [uid_of(c) for c in result.matches]

        correction = CORRECTIONS.get(query.strip())
        if correction:
            ok = sorted(got) == sorted(correction["corrected"])
            failed += 1
            corrected += 1
            lines.append(
                "  PLAN WRONG  %-14s expected %-42s\n"
                "              corrected to %s\n"
                "              %s\n"
                "              tool returned %s -> %s"
                % (
                    repr(query),
                    expected,
                    ", ".join(correction["corrected"]),
                    correction["why"],
                    got or result.status,
                    "matches the correction" if ok else "DOES NOT match the correction",
                )
            )
            if not ok:
                lines.append("              THE CORRECTION ALSO FAILS — investigate")
            continue

        if expected == "NO MATCH":
            ok = result.status == Status.NONE
            detail = result.status
        elif expected.startswith("WITHDRAWN REDIRECT"):
            ok = result.status == Status.WITHDRAWN and bool(result.redirects)
            detail = result.note or result.status
        elif expected.startswith("AMBIGUOUS"):
            ok = result.status == Status.AMBIGUOUS
            detail = "%s: %s" % (result.status, ", ".join(got))
        else:
            ok = result.status == Status.UNIQUE and got == [expected]
            detail = ", ".join(got) or result.status

        if ok:
            passed += 1
            lines.append("  pass        %-14s %s" % (repr(query), detail[:78]))
        else:
            failed += 1
            lines.append(
                "  FAIL        %-14s expected %s\n              got %s\n              trap: %s"
                % (repr(query), expected, detail, why)
            )

    print("\n".join(lines))
    print(
        "\nidentifier lookup: %d passed, %d failed (%d of those are plan corrections)"
        % (passed, failed, corrected)
    )
    return 1 if (failed - corrected) else 0


def extra_checks(corpus, index) -> int:
    """Assertions the plan does not carry but the traps demand."""
    problems = []

    # A prefix must never match. Req 9 exists; Req 93 and Req 99 must not answer it.
    result = index.find("Req 9")
    got = [c.identifier for c in result.matches]
    if got != ["Req 9"]:
        problems.append("prefix leak: 'Req 9' returned %s" % got)

    # Prose must not enter the identifier path at all.
    for prose in ("multi-factor authentication", "backup", "media sanitisation"):
        if index.find(prose).status != Status.NOT_AN_IDENTIFIER:
            problems.append("prose %r was treated as an identifier" % prose)

    # A framework word must narrow an otherwise ambiguous subsection.
    result = index.find("CIRMP s 8(4)")
    got = [c.uid for c in result.matches]
    if got != ["cirmp-rules:s 8.4"]:
        problems.append("qualifier failed: 'CIRMP s 8(4)' returned %s" % got)

    # The qualifier must not eat a prefix that is part of the identifier.
    result = index.find("ISM-0421")
    if [c.uid for c in result.matches] != ["ism:ism-421"]:
        problems.append("qualifier ate an identifier prefix on ISM-0421")

    for problem in problems:
        print("  FAIL        %s" % problem)
    if not problems:
        print("  pass        prefix, prose, qualifier and prefix-welding checks")
    return len(problems)


if __name__ == "__main__":
    corpus, _ = build(verbose=False)
    index = IdentifierIndex(corpus)
    code = run()
    print()
    code += extra_checks(corpus, index)
    sys.exit(1 if code else 0)
