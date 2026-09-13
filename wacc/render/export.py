"""Exports. What a person pastes into a working paper or a finding.

Two formats, both plain text so they survive a locked-down machine with no Office
automation: comma-separated values for a spreadsheet, and markdown for a document. Both
carry provenance on every row, because an exported row that has lost its fidelity and
provenance is a claim with no source, and it is the row that ends up quoted.
"""

import csv
import io
from typing import List, Optional, Sequence

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
    for band in analysis.bands:
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

    for band in analysis.bands:
        out.append("## Tier %d — %s" % (band.tier.value, band.tier.label))
        out.append("")
        out.append("*%s*" % band.tier.question)
        out.append("")
        if band.is_empty:
            out.append("Nothing found at this tier. The band is shown because an "
                       "omitted band reads as a question nobody asked.")
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
