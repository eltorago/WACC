"""The terminal renderer.

Written for a person reading at a prompt on a locked-down machine, which is where this
tool mostly runs. Every band is drawn including the empty ones, because a band that is not
drawn reads as a question nobody asked.
"""

from typing import List, Optional, Sequence

from ..analysis import Analysis
from ..model import Corpus

RULE = "-" * 78


def _wrap(text: str, width: int, indent: str = "") -> List[str]:
    words = (text or "").split()
    lines: List[str] = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width and current.strip():
            lines.append(current.rstrip())
            current = indent + word
        else:
            current = (current + " " + word) if current.strip() else indent + word
    if current.strip():
        lines.append(current.rstrip())
    return lines


def render(corpus: Corpus, analysis: Analysis, width: int = 78, show: int = 3) -> str:
    out: List[str] = []
    out.append(RULE)
    # Wrapped, because a pasted control is a legitimate subject and an unwrapped one
    # would run off the terminal.
    subject_lines = _wrap(analysis.subject or "(no subject)", width - 9)
    out.append("SUBJECT  %s" % (subject_lines[0] if subject_lines else ""))
    for line in subject_lines[1:]:
        out.append("         %s" % line)
    from ..framework_families import count as family_count
    speaking = family_count(cov.framework.key for band in analysis.bands for cov in band.coverage if cov.total)
    absent = analysis.frameworks_absent
    out.extend(_wrap(
        "%d source records shown of %d read, across %d of %d framework families in this build"
        % (len(analysis.controls), analysis.depth, speaking,
           analysis.frameworks_present), width, "         "
    ))
    if absent:
        # Said on the second line of every result, because a build missing half its
        # corpora answers a narrower question than the one that was asked.
        out.append(
            "         %d of %d registered frameworks are not in this build"
            % (len(absent), len(corpus.frameworks))
        )
    out.append(RULE)

    for band in analysis.bands:
        out.append("")
        out.append("TIER %d  %s" % (band.tier.value, band.tier.label.upper()))
        out.append("        %s" % band.tier.question)
        if band.is_empty:
            out.append("        nothing found at this tier")
            continue
        for coverage in band.coverage:
            if coverage.absent:
                out.append(
                    "  %-14s not in this build" % coverage.framework.short_name
                )
                continue
            if coverage.is_empty:
                out.append("  %-14s -" % coverage.framework.short_name)
                continue
            out.append(
                "  %-14s %d control%s"
                % (
                    coverage.framework.short_name,
                    coverage.total,
                    "" if coverage.total == 1 else "s",
                )
            )
            for control in coverage.controls[:show]:
                head = "      %-18s " % control.identifier
                body = (control.title or control.text or "").strip()
                wrapped = _wrap(body, width - len(head), "")
                out.append(head + (wrapped[0] if wrapped else ""))
                for line in wrapped[1:2]:
                    out.append(" " * len(head) + line)
            more = (len(coverage.controls) - show) + coverage.hidden
            if more > 0:
                out.append("      %-18s and %d more" % ("", more))

    silent = analysis.frameworks_silent
    if silent:
        out.append("")
        out.append("SAYS NOTHING ON THIS SUBJECT")
        out.extend(_wrap(", ".join(f.short_name for f in silent), width, "  "))

    if analysis.frameworks_absent:
        out.append("")
        out.append("NOT IN THIS BUILD")
        out.extend(
            _wrap(
                "These are registered and were not loaded, so nothing above says what "
                "they require. This is not the same as saying nothing.",
                width, "  ",
            )
        )
        for framework, reason in analysis.frameworks_absent:
            out.extend(_wrap("%s: %s" % (framework.short_name, reason), width, "    "))

    if analysis.comparisons:
        out.append("")
        out.append("FIGURES STATED")
        for comparison in analysis.comparisons:
            out.append(
                "  %-12s %d stated" % (comparison.dimension, len(comparison.thresholds))
            )
            # A threshold's own description carries its caveats and can be longer than a
            # terminal line on its own, so these wrap like everything else.
            for label, threshold in (
                ("strictest", comparison.strictest),
                ("loosest", comparison.loosest),
            ):
                if threshold is None:
                    continue
                if label == "loosest" and threshold is comparison.strictest:
                    continue
                out.extend(
                    _wrap(
                        "%-10s %s  [%s]"
                        % (label, threshold.describe(), threshold.control_uid),
                        width,
                        "      ",
                    )
                )
            if comparison.note:
                out.extend(_wrap(comparison.note, width, "      "))

    if analysis.disagreements:
        out.append("")
        out.append(
            "DIFFERENT FIGURES ON THIS SUBJECT (%d)" % len(analysis.disagreements)
        )
        incompatible = analysis.incompatible_bounds
        for disagreement in analysis.disagreements[:show]:
            for line in disagreement.describe(corpus).split("\n"):
                out.extend(_wrap(line, width, "  "))
            out.append("")
        if len(analysis.disagreements) > show:
            out.append("  and %d more" % (len(analysis.disagreements) - show))
        if incompatible:
            out.append(
                "  %d pair%s cannot both be met if they govern the same requirement."
                % (len(incompatible), "" if len(incompatible) == 1 else "s")
            )

    if analysis.attributions:
        out.append("")
        out.append("ACKNOWLEDGEMENTS")
        for name, wording in analysis.attributions:
            out.extend(_wrap("%s: %s" % (name, wording), width, "  "))

    if analysis.notes:
        out.append("")
        out.append("NOTES")
        for note in analysis.notes:
            out.extend(_wrap(note, width, "  "))
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_control(corpus: Corpus, derivation, placement=None, lineage=None,
                   width: int = 78) -> str:
    """One control in full: what it says, where it sits, what it connects to, how to test."""
    control = derivation.control
    framework = corpus.frameworks[control.framework_key]
    out = [RULE, "%s %s" % (framework.short_name, control.identifier)]
    if control.title and not control.title_is_shared:
        out.append(control.title)
    out.append(RULE)
    out.extend(_wrap((control.text or "").strip(), width))

    if placement is not None and placement.needs_its_parent:
        out.append("")
        out.append("QUOTE AS")
        out.extend(_wrap(placement.quotable, width, "  "))

    if lineage is not None:
        out.append("")
        out.append("WHAT ELSE STATES THIS")
        for band in lineage.bands:
            if band.is_empty:
                out.append("  %-14s -" % band.provenance.value)
                out.extend(_wrap(band.note, width, "      "))
                continue
            out.append("  %-14s %d" % (band.provenance.value, len(band.relations)))
            for relation in band.relations[:4]:
                out.append(
                    "      %-26s %s"
                    % (relation.other.uid, relation.direction_note(corpus)[:44])
                )

    if derivation.refusal is not None:
        out.append("")
        out.append("NOT TESTABLE")
        out.extend(_wrap(derivation.refusal.detail, width, "  "))
        return "\n".join(out) + "\n"

    if derivation.published:
        out.append("")
        out.append("PUBLISHED TEST PROCEDURE (%s)" % derivation.published[0].published_by)
        for statement in derivation.published[:1]:
            out.extend(_wrap(statement.text[:600], width, "  "))

    if derivation.derived_tests:
        out.append("")
        out.append("DERIVED TEST PROCEDURE")
        for statement in derivation.derived_tests:
            out.append("  [%s]" % statement.archetype)
            out.extend(_wrap(statement.text, width, "    "))
            out.append("")

    if derivation.risk is not None:
        out.append("IF THIS CONTROL IS ABSENT")
        out.extend(_wrap(derivation.risk.text, width, "  "))
    return "\n".join(out).rstrip() + "\n"
