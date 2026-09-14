"""Exports. What a person pastes into a working paper or a finding.

Two formats, both plain text so they survive a locked-down machine with no Office
automation: comma-separated values for a spreadsheet, and markdown for a document. Both
carry provenance on every row, because an exported row that has lost its fidelity and
provenance is a claim with no source, and it is the row that ends up quoted.
"""

from .groups import result_groups, group_label
import csv
import io
from typing import Dict, List, Optional, Sequence

from ..analysis import Analysis
from ..model import Corpus, Provenance

# Jurisdiction.WA is 0, so `if framework.jurisdiction` is False for every Western
# Australian framework and the export dropped the jurisdiction from exactly the rows a WA
# entity reads first. Comparisons against None, not truthiness, wherever an enum can be
# zero.
COLUMNS = [
    "tier",
    "tier_label",
    "framework",
    "jurisdiction",
    "identifier",
    "title",
    "text",
    "obligation",
    "obligation_provenance",
    "publisher_tiering",
    "fidelity",
    "source_file",
    "applies_to",
]


def _row(corpus: Corpus, control, reading=None) -> List[str]:
    framework = corpus.frameworks[control.framework_key]
    from ..analysis import currency_of

    currency = "; ".join("%s: %s" % pair for pair in currency_of(control))
    return [
        str(framework.tier.value) if framework.tier is not None else "",
        framework.tier.label if framework.tier is not None else "",
        framework.short_name,
        framework.jurisdiction.name if framework.jurisdiction is not None else "",
        control.identifier,
        (control.title or "") if not control.title_is_shared else "",
        " ".join((control.text or "").split()),
        control.obligation.value,
        control.obligation_provenance.value,
        currency,
        control.fidelity.value if control.fidelity else "",
        framework.source_file or "",
        control.applicability_text(),
    ]


def to_csv(corpus: Corpus, analysis: Analysis) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["subject", analysis.subject])
    writer.writerow(
        ["controls shown", len(analysis.controls), "controls read", analysis.depth]
    )
    writer.writerow([])
    writer.writerow(COLUMNS)
    for band in result_groups(analysis):
        for coverage in band.coverage:
            for control in coverage.controls:
                writer.writerow(_row(corpus, control))

    if analysis.attributions:
        writer.writerow([])
        writer.writerow(["acknowledgements required by the publishers of this content"])
        for name, wording in analysis.attributions:
            writer.writerow([name, wording])

    silent = analysis.frameworks_silent
    if silent:
        writer.writerow([])
        writer.writerow(["frameworks that say nothing on this subject"])
        for framework in silent:
            writer.writerow(
                [
                    str(framework.tier.value) if framework.tier is not None else "",
                    framework.tier.label if framework.tier is not None else "",
                    framework.short_name,
                    "",
                    "",
                    "nothing found",
                ]
            )

    if analysis.frameworks_absent:
        writer.writerow([])
        writer.writerow(
            ["frameworks registered but not loaded in this build — "
             "nothing above says what these require"]
        )
        for framework, reason in analysis.frameworks_absent:
            writer.writerow(
                [
                    str(framework.tier.value) if framework.tier is not None else "",
                    framework.tier.label if framework.tier is not None else "",
                    framework.short_name,
                    "",
                    "",
                    "not in this build",
                    reason,
                ]
            )
    return buffer.getvalue()


def to_markdown(corpus: Corpus, analysis: Analysis) -> str:
    out: List[str] = ["# %s" % analysis.subject, ""]
    out.append(
        "%d controls shown of %d read, across %d frameworks."
        % (
            len(analysis.controls),
            analysis.depth,
            len({c.framework_key for c in analysis.controls}),
        )
    )
    out.append("")

    for band in result_groups(analysis):
        out.append("## %s" % group_label(band))
        out.append("")
        out.append("")
        if band.is_empty:
            out.append("No matching controls in this group.")
            out.append("")
            continue
        out.append("| Framework | Identifier | Requirement | Publisher states |")
        out.append("|---|---|---|---|")
        for coverage in band.coverage:
            for control in coverage.controls:
                from ..analysis import currency_of

                currency = "; ".join("%s: %s" % pair for pair in currency_of(control))
                if not currency:
                    currency = (
                        control.obligation.value
                        if control.obligation_provenance is Provenance.PUBLISHED
                        else "%s (read from the wording by this tool)"
                        % control.obligation.value
                    )
                text = " ".join((control.text or "").split())
                out.append(
                    "| %s | %s | %s | %s |"
                    % (
                        _cell(coverage.framework.short_name),
                        _cell(control.identifier),
                        _cell(text),
                        _cell(currency),
                    )
                )
        out.append("")

    silent = analysis.frameworks_silent
    if silent:
        out.append("## Says nothing on this subject")
        out.append("")
        out.append(", ".join(f.short_name for f in silent) + ".")
        out.append("")

    if analysis.frameworks_absent:
        # An exported table is what gets pasted into a finding, so the difference between
        # "read and silent" and "not read at all" has to survive the export.
        out.append(
            "## Not in this build (%d of %d registered frameworks)"
            % (len(analysis.frameworks_absent), len(corpus.frameworks))
        )
        out.append("")
        out.append(
            "Nothing above says what these require. That is not the same as saying "
            "nothing."
        )
        out.append("")
        for framework, reason in analysis.frameworks_absent:
            out.append("- **%s** — %s" % (framework.short_name, reason))
        out.append("")

    if analysis.comparisons:
        out.append("## Figures stated")
        out.append("")
        for comparison in analysis.comparisons:
            if comparison.strictest:
                out.append(
                    "- %s: strictest is %s, in %s."
                    % (
                        comparison.dimension,
                        comparison.strictest.describe(),
                        comparison.strictest.control_uid,
                    )
                )
            if comparison.note:
                out.append("  - %s" % comparison.note)
        out.append("")

    if analysis.disagreements:
        out.append("## Different figures on this subject")
        out.append("")
        for disagreement in analysis.disagreements[:8]:
            out.append("- " + disagreement.describe(corpus).replace("\n     ", " — "))
        out.append("")

    if analysis.attributions:
        out.append("## Acknowledgements")
        out.append("")
        for name, wording in analysis.attributions:
            out.append("- **%s** — %s" % (name, wording))
        out.append("")

    if analysis.notes:
        out.append("## Notes")
        out.append("")
        for note in analysis.notes:
            out.append("- %s" % note)
        out.append("")
    return "\n".join(out)


def _cell(text: str, limit: int = 260) -> str:
    """A markdown cell cannot hold a pipe or a newline and stay a cell."""
    text = " ".join((text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --------------------------------------------------------------------------
# Two working papers: one for an executive, one for the person doing the test
# --------------------------------------------------------------------------

# Every generated paper carries this. Not a disclaimer for its own sake — the tool states
# the consequence side of a risk and nothing about likelihood, and a reader who takes a
# consequence statement for a risk rating has been misled by the omission.
RISK_CAVEAT = (
    "This states the consequence side only. Whether any of it is likely depends on the "
    "entity's exposure and the controls actually in place, neither of which this tool "
    "knows. Control wording is quoted from the documents named; confirm it against the "
    "published source before relying on it."
)

TEST_CAVEAT = (
    "Steps are derived from each control's own wording and the shape of requirement it "
    "is, not from a published audit programme, except where a procedure is marked as its "
    "publisher's. They give the shape of the test; the systems in scope and the evidence "
    "that will satisfy it are yours to decide."
)


def risk_summary(corpus: Corpus, analysis: Analysis, risks: Dict[str, object]) -> str:
    """What is exposed if the controls on this subject are absent, for an executive.

    Ordered governance-first, because a statutory provision and a benchmark setting are
    not the same kind of exposure and reading them in that order is how the reader tells.
    """
    out: List[str] = ["# Risk summary: %s" % analysis.subject, ""]
    out.append(
        "%d controls across %d frameworks state a requirement on this subject."
        % (len(analysis.controls), len({c.framework_key for c in analysis.controls}))
    )
    out.append("")

    silent = analysis.frameworks_silent
    if silent:
        out.append(
            "Loaded and silent on it: %s. Those publishers were asked and require "
            "nothing here."
            % ", ".join(f.short_name for f in silent)
        )
        out.append("")
    if analysis.frameworks_absent:
        out.append(
            "Not in this build, so not asked: %s. Absence here is not evidence that "
            "nothing is required."
            % ", ".join(f.short_name for f, _ in analysis.frameworks_absent)
        )
        out.append("")

    for band in result_groups(analysis):
        stated = [c for coverage in band.coverage for c in coverage.controls]
        if not stated:
            continue
        out.append("## %s" % group_label(band))
        out.append("")
        for control in stated:
            statement = risks.get(control.uid)
            if statement is None:
                continue
            framework = corpus.frameworks[control.framework_key]
            out.append(
                "**%s %s** — %s"
                % (framework.short_name, control.identifier,
                   " ".join(str(getattr(statement, "text", statement)).split()))
            )
            out.append("")

    if analysis.incompatible_bounds:
        out.append("## Figures that cannot both be met")
        out.append("")
        for disagreement in analysis.incompatible_bounds:
            out.append("- " + disagreement.describe(corpus).replace("\n     ", " — "))
        out.append("")

    if analysis.attributions:
        out.append("## Acknowledgements")
        out.append("")
        for name, wording in analysis.attributions:
            out.append("- **%s** — %s" % (name, wording))
        out.append("")

    out.append("---")
    out.append("")
    out.append(RISK_CAVEAT)
    return "\n".join(out)


def test_plan(corpus: Corpus, analysis: Analysis, derivations: Dict[str, object]) -> str:
    """A workpaper: one section per control, with somewhere to record the result.

    The sign-off table is the reason this is a file rather than a screen. A test nobody
    recorded the result of was not carried out, and a plan with no place to write it
    invites the result to live in an email.
    """
    out: List[str] = ["# Test plan: %s" % analysis.subject, ""]
    out.append(TEST_CAVEAT)
    out.append("")

    current = None
    for control in analysis.controls:
        derivation = derivations.get(control.uid)
        if derivation is None:
            continue
        framework = corpus.frameworks[control.framework_key]
        if framework.key != current:
            current = framework.key
            out.append("## %s%s" % (framework.name,
                                    " (%s)" % framework.revision if framework.revision else ""))
            out.append("")

        out.append("### %s" % control.identifier)
        out.append("")
        out.append("> %s" % " ".join((control.text or control.title or "").split()))
        out.append("")

        refusal = getattr(derivation, "refusal", None)
        if refusal is not None:
            out.append("No test derived. %s — %s" % (refusal.reason, refusal.detail))
            out.append("")

        for material in getattr(derivation, "related_assessments", []):
            source = material.control
            out.append("**Related assessment: %s %s — %s**" % (
                corpus.frameworks[source.framework_key].short_name, source.identifier,
                source.title or "Assessment material"))
            out.append("Connection: %s. %s" % (material.connection.value, material.basis))
            out.append("")
            for statement in material.statements:
                out.append("**%s**" % statement.published_by)
                out.append(statement.text)
                out.append("")

        for statement in getattr(derivation, "published", []):
            out.append("**Published procedure — %s**" % (statement.published_by or "publisher"))
            out.append("")
            out.append(" ".join(statement.text.split()))
            out.append("")
        for statement in getattr(derivation, "derived_tests", []):
            out.append("**Derived procedure**")
            out.append("")
            out.append(" ".join(statement.text.split()))
            out.append("")

        risk = getattr(derivation, "risk", None)
        if risk is not None:
            out.append("**If absent:** %s" % " ".join(risk.text.split()))
            out.append("")

        detail = getattr(derivation, "detail", [])
        if detail:
            out.append("**Product detail (CIS benchmark text, import-only)**")
            out.append("")
            for item in detail[:6]:
                out.append("- %s %s — %s" % (item.source_key, item.identifier, item.title))
            out.append("")

        out.append("| Tested by | Date | Result | Workpaper reference |")
        out.append("| --- | --- | --- | --- |")
        out.append("|  |  |  |  |")
        out.append("")

    out.append("---")
    out.append("")
    out.append(RISK_CAVEAT)
    return "\n".join(out)
