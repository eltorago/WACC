"""The results screen: a crosswalk grid, rendered as one self-contained page.

Standard library only, no framework, no network. The page is written whole and opened from
disk or served from localhost, because nothing may leave the machine.

The grid is the point. The pinned left column names the tier band and the question a reader
is asking at that tier; each remaining column is a framework in governance order; a cell
holds what that framework says on the subject. Sixteen frameworks never all fit, so the
grid scrolls sideways and the left column stays put — see wacc/render/layout.py for the
column arithmetic and the measurements behind it.

Two densities, because they answer different questions. Comfortable shows the control text
for reading one requirement properly. Compact shows the identifier, the obligation the
publisher states, its tags and two clamped lines, for seeing how far a subject reaches
across every document at once. The choice is remembered in localStorage, so a reader who
prefers compact does not re-choose it on every search.

Column headers are clamped to one line and carry the full name in a title attribute, since
a header that wraps changes the height of every row in the grid.
"""

import html as _html
import urllib.parse
from typing import List, Optional

from ..analysis import Analysis, currency_of
from ..model import Control, Corpus, Provenance
from .layout import COLUMN_GAP, COMFORTABLE, COMPACT, PAGE_PADDING, PINNED

STYLE = """
:root {
  --pinned: %(pinned)dpx;
  --comfortable: %(comfortable)dpx;
  --compact: %(compact)dpx;
  --gap: %(gap)dpx;
  --pad: %(pad)dpx;
  --ink: #1a1a1a;
  --quiet: #666;
  --rule: #d8d8d8;
  --band: #f4f4f2;
  --empty: #fafaf8;
  --derived: #8a6d1f;
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: var(--pad);
  font: 14px/1.45 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--ink); background: #fff;
}
h1 { font-size: 18px; margin: 0 0 2px; font-weight: 600; }
.sub { color: var(--quiet); margin-bottom: 14px; }
form { margin: 0 0 14px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
input[type=search] {
  width: 420px; max-width: 100%%; padding: 7px 10px;
  border: 1px solid var(--rule); border-radius: 3px; font: inherit;
}
button {
  padding: 7px 12px; border: 1px solid var(--rule); background: #fff;
  border-radius: 3px; font: inherit; cursor: pointer;
}
button[aria-pressed=true] { background: var(--ink); color: #fff; border-color: var(--ink); }

/* The grid scrolls sideways; the pinned column does not move. Widths are pixels, never
   vw, so a wider screen buys more frameworks rather than wider text. */
.scroll { overflow-x: auto; border: 1px solid var(--rule); border-radius: 3px; }
table { border-collapse: separate; border-spacing: 0; }
th, td {
  vertical-align: top; padding: 8px 10px;
  border-bottom: 1px solid var(--rule); border-right: 1px solid var(--rule);
}
th.pin, td.pin {
  position: sticky; left: 0; z-index: 2; background: var(--band);
  width: var(--pinned); min-width: var(--pinned); max-width: var(--pinned);
}
thead th { position: sticky; top: 0; z-index: 3; background: #fff; text-align: left; }
thead th.pin { z-index: 4; background: var(--band); }
thead th span {
  display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
td.col, th.col {
  width: var(--comfortable); min-width: var(--comfortable); max-width: var(--comfortable);
}
body[data-density=compact] td.col, body[data-density=compact] th.col {
  width: var(--compact); min-width: var(--compact); max-width: var(--compact);
}
.ident { font-weight: 600; font-variant-numeric: tabular-nums; }
.states { color: var(--quiet); font-size: 12px; margin-top: 2px; }
.states .derived { color: var(--derived); }
.body { margin-top: 4px; }
body[data-density=compact] .body {
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
body[data-density=comfortable] .states.tags { display: none; }
.more { color: var(--quiet); font-size: 12px; margin-top: 6px; }
td.none { background: var(--empty); color: var(--quiet); font-size: 12px; }
td.missing {
  background: #fdf6e7; color: var(--derived); font-size: 12px;
}
td.missing .why { color: var(--quiet); margin-top: 3px; }
tr.band td.pin .q { color: var(--quiet); font-weight: 400; font-size: 12px; }
section { margin-top: 22px; }
section h2 { font-size: 14px; margin: 0 0 6px; }
ul { margin: 0 0 10px; padding-left: 18px; }
li { margin-bottom: 4px; }
.note { color: var(--quiet); }
""" % {
    "pinned": PINNED,
    "comfortable": COMFORTABLE,
    "compact": COMPACT,
    "gap": COLUMN_GAP,
    "pad": PAGE_PADDING,
}

SCRIPT = """
(function () {
  var KEY = 'wacc-density';
  function apply(value) {
    document.body.dataset.density = value;
    document.querySelectorAll('[data-set-density]').forEach(function (button) {
      button.setAttribute('aria-pressed',
        String(button.dataset.setDensity === value));
    });
  }
  var saved = 'comfortable';
  try { saved = localStorage.getItem(KEY) || 'comfortable'; } catch (e) {}
  apply(saved);
  document.querySelectorAll('[data-set-density]').forEach(function (button) {
    button.addEventListener('click', function () {
      var value = button.dataset.setDensity;
      apply(value);
      try { localStorage.setItem(KEY, value); } catch (e) {}
    });
  });
})();
"""


def esc(value: Optional[str]) -> str:
    return _html.escape(value or "", quote=True)


def _states(control: Control) -> str:
    """What the publisher says about how binding this is, in the publisher's own terms."""
    currency = currency_of(control)
    if currency:
        return esc("; ".join("%s: %s" % pair for pair in currency))
    if control.obligation_provenance is Provenance.PUBLISHED:
        return esc(control.obligation.value)
    return '<span class="derived">%s, read from the wording</span>' % esc(
        control.obligation.value
    )


def _cell(corpus: Corpus, coverage) -> str:
    if coverage.absent:
        # Three kinds of empty, not two. A framework that is not in the build says
        # nothing because nobody looked, and drawing it like a framework that was read
        # and had nothing to say understates every obligation it carries.
        return '<td class="col missing">not in this build<div class="why">%s</div></td>' % esc(
            coverage.absent
        )
    if coverage.is_empty:
        if coverage.total:
            return '<td class="col none">nothing in the shown set</td>'
        return '<td class="col none">says nothing on this subject</td>'
    parts = []
    for control in coverage.controls[:4]:
        body = " ".join((control.text or control.title or "").split())
        parts.append(
            '<div class="entry"><span class="ident">%s</span>'
            '<div class="states">%s</div>'
            '<div class="body">%s</div></div>'
            % (esc(control.identifier), _states(control), esc(body))
        )
    hidden = coverage.hidden + max(0, len(coverage.controls) - 4)
    if hidden:
        parts.append('<div class="more">and %d more</div>' % hidden)
    return '<td class="col">%s</td>' % "".join(parts)


def render(corpus: Corpus, analysis: Analysis, title: str = "WA Control Crosswalk") -> str:
    frameworks = [
        coverage.framework
        for band in analysis.bands
        for coverage in band.coverage
    ]
    seen = []
    for framework in frameworks:
        if framework.key not in [f.key for f in seen]:
            seen.append(framework)

    head = ['<th class="pin"><span>Tier</span></th>']
    for framework in seen:
        head.append(
            '<th class="col" title="%s"><span>%s</span></th>'
            % (esc(framework.name), esc(framework.short_name))
        )

    rows = []
    for band in analysis.bands:
        by_key = {c.framework.key: c for c in band.coverage}
        cells = [
            '<td class="pin"><div>Tier %d — %s</div><div class="q">%s</div></td>'
            % (band.tier.value, esc(band.tier.label), esc(band.tier.question))
        ]
        for framework in seen:
            coverage = by_key.get(framework.key)
            cells.append(
                _cell(corpus, coverage)
                if coverage is not None
                else '<td class="col none">not at this tier</td>'
            )
        rows.append('<tr class="band">%s</tr>' % "".join(cells))

    sections = []
    if analysis.comparisons:
        items = []
        for comparison in analysis.comparisons:
            if comparison.strictest:
                items.append(
                    "<li><strong>%s</strong>: strictest is %s, in %s.</li>"
                    % (
                        esc(comparison.dimension),
                        esc(comparison.strictest.describe()),
                        esc(comparison.strictest.control_uid),
                    )
                )
            if comparison.note:
                items.append('<li class="note">%s</li>' % esc(comparison.note))
        sections.append("<section><h2>Figures stated</h2><ul>%s</ul></section>"
                        % "".join(items))

    if analysis.disagreements:
        items = [
            "<li>%s</li>" % esc(d.describe(corpus).replace("\n     ", " — "))
            for d in analysis.disagreements[:8]
        ]
        sections.append(
            "<section><h2>Different figures on this subject (%d)</h2><ul>%s</ul></section>"
            % (len(analysis.disagreements), "".join(items))
        )

    if analysis.frameworks_absent:
        sections.append(
            "<section><h2>Not in this build (%d of %d)</h2>"
            "<p class=\"note\">These frameworks are registered and were not loaded, so "
            "nothing above says what they require. That is not the same as saying "
            "nothing.</p><ul>%s</ul></section>"
            % (
                len(analysis.frameworks_absent),
                len(corpus.frameworks),
                "".join(
                    "<li><strong>%s</strong> — %s</li>" % (esc(f.short_name), esc(why))
                    for f, why in analysis.frameworks_absent
                ),
            )
        )

    if analysis.attributions:
        sections.append(
            "<section><h2>Acknowledgements</h2><ul>%s</ul></section>"
            % "".join(
                "<li><strong>%s</strong> — %s</li>" % (esc(name), esc(wording))
                for name, wording in analysis.attributions
            )
        )

    if analysis.notes:
        sections.append(
            "<section><h2>Notes</h2><ul>%s</ul></section>"
            % "".join('<li class="note">%s</li>' % esc(n) for n in analysis.notes)
        )

    speaking = sum(1 for b in analysis.bands for c in b.coverage if c.total)
    missing = len(analysis.frameworks_absent)
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>%(title)s</title><style>%(style)s</style></head>"
        "<body data-density=\"comfortable\">"
        "<h1>%(title)s</h1>"
        "<div class=\"sub\">%(subject)s — %(shown)d controls shown of %(read)d read, "
        "across %(speaking)d of %(present)d frameworks in this build%(missing)s</div>"
        "<form method=\"get\" action=\"/\">"
        "<input type=\"search\" name=\"q\" value=\"%(query)s\" "
        "placeholder=\"a subject, or a control identifier\" autofocus>"
        "<button type=\"submit\">Search</button>"
        "<button type=\"button\" data-set-density=\"comfortable\">Comfortable</button>"
        "<button type=\"button\" data-set-density=\"compact\">Compact</button>"
        "<a href=\"/export.csv?q=%(url_query)s\">CSV</a>"
        "<a href=\"/export.md?q=%(url_query)s\">Markdown</a>"
        "</form>"
        "<div class=\"scroll\"><table><thead><tr>%(head)s</tr></thead>"
        "<tbody>%(rows)s</tbody></table></div>"
        "%(sections)s"
        "<script>%(script)s</script></body></html>"
        % {
            "title": esc(title),
            "style": STYLE,
            "subject": esc(analysis.subject),
            "shown": len(analysis.controls),
            "read": analysis.depth,
            "speaking": speaking,
            "present": analysis.frameworks_present,
            "total": len(corpus.frameworks),
            "missing": (
                " · %d of %d registered frameworks are not in this build"
                % (missing, len(corpus.frameworks))
            ) if missing else "",
            "query": esc(analysis.subject),
            # Escaping is for the page; a query carrying an ampersand also has to survive
            # being a query string, and HTML escaping does not do that.
            "url_query": urllib.parse.quote(analysis.subject or "", safe=""),
            "head": "".join(head),
            "rows": "".join(rows),
            "sections": "".join(sections),
            "script": SCRIPT,
        }
    )
