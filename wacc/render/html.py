"""The results screen: a crosswalk grid and a card view, rendered as one page.

Standard library only, no framework, no network. The page is written whole and opened from
disk or served from localhost, because nothing may leave the machine.

Two views, because a crosswalk is asked two different questions and one layout answers them
badly. The grid pins a tier column and puts each framework in a column beside it, so a
reader sees how far a subject reaches across the abstraction spine — statute to technical
specification — at a glance. The cards drop the tier column, widen the columns and put the
control text, the publisher's tags, the risk statement and the test procedure in one place,
for reading a single requirement properly. Neither is a better layout; they are answers to
'how far does this reach' and 'what does this one actually require'. See
wacc/render/layout.py for both column counts and the widths they were measured at.

What the view is and how many controls are shown are in the URL, so a page can be sent to
someone. Density and which frameworks are hidden are in localStorage, because they are how
one person likes to read rather than part of the question being asked.

The page fetches one thing and only from itself: the panel under a control, which carries
the test procedure, the links and any product detail, and is loaded when a reader opens it
rather than for every control on screen. It arrives as HTML rather than JSON so that the
escaping and the wording both stay in Python where the suite can read them.
"""

import html as _html
import urllib.parse
from typing import Dict, List, Optional, Sequence, Tuple

from ..analysis import Analysis, currency_of
from ..model import Control, Corpus, Fidelity, Provenance, Statement
from ..terms import CONCEPTS, prepare
from .highlight import mark
from .groups import result_groups, group_label
from .layout import (
    CARD_COMFORTABLE,
    CARD_COMPACT,
    COLUMN_GAP,
    COMFORTABLE,
    COMPACT,
    PAGE_PADDING,
    PINNED,
)

# How many controls a framework column shows before it says how many more it read.
PER_FRAMEWORK = 4
LIMIT_CHOICES = (10, 25, 50)

STYLE = """
:root {
  --pinned: %(pinned)dpx;
  --comfortable: %(comfortable)dpx;
  --compact: %(compact)dpx;
  --card: %(card)dpx;
  --card-compact: %(card_compact)dpx;
  --gap: %(gap)dpx;
  --pad: %(pad)dpx;
  --ink: #1a1a1a;
  --quiet: #666;
  --rule: #d8d8d8;
  --band: #f4f4f2;
  --empty: #fafaf8;
  --derived: #8a6d1f;
  --paper: #fff;
  --panel: #fbfbf9;
  --mark: #fff2a8;
  --mark-wide: #eef1f5;
  --absent: #fdf6e7;
  --risk: #b3261e;
  --link: #1f4fd8;
}
/* The tool is read for hours at a time against a wall of grey control text. The dark
   palette is the same design with the roles swapped, not a second design. */
@media (prefers-color-scheme: dark) {
  :root {
    --ink: #e6e7ea;
    --quiet: #9aa0aa;
    --rule: #2f343d;
    --band: #1b1f26;
    --empty: #15181e;
    --derived: #d7ab4a;
    --paper: #101317;
    --panel: #171b21;
    --mark: #5a4a00;
    --mark-wide: #23282f;
    --absent: #2a2313;
    --risk: #f08079;
    --link: #86a6ff;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: var(--pad);
  font: 14px/1.45 -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  color: var(--ink); background: var(--paper);
}
a { color: var(--link); }
h1 { font-size: 18px; margin: 0 0 2px; font-weight: 600; }
.sub { color: var(--quiet); margin-bottom: 14px; }
form { margin: 0 0 10px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
input[type=search] {
  width: 420px; max-width: 100%%; padding: 7px 10px;
  border: 1px solid var(--rule); border-radius: 3px; font: inherit;
  background: var(--paper); color: var(--ink);
}
select { font: inherit; padding: 6px; border: 1px solid var(--rule); border-radius: 3px;
  background: var(--paper); color: var(--ink); }
button, .btn {
  padding: 7px 12px; border: 1px solid var(--rule); background: var(--paper);
  border-radius: 3px; font: inherit; cursor: pointer; color: var(--ink);
  text-decoration: none; display: inline-block;
}
button[aria-pressed=true], .btn[aria-pressed=true] {
  background: var(--ink); color: var(--paper); border-color: var(--ink);
}
mark.mark { background: var(--mark); color: inherit; padding: 0 1px; border-radius: 2px; }
mark.wide { background: var(--mark-wide); color: inherit; }

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
thead th { position: sticky; top: 0; z-index: 3; background: var(--paper); text-align: left; }
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
td.missing { background: var(--absent); color: var(--derived); font-size: 12px; }
td.missing .why { color: var(--quiet); margin-top: 3px; }
tr.band td.pin .q { color: var(--quiet); font-weight: 400; font-size: 12px; }

/* Cards. Each column is one framework; the column width is the layout constant and the
   cards inside it stack. No pinned column, so every pixel buys frameworks. */
.cards { display: flex; gap: var(--gap); align-items: flex-start; overflow-x: auto;
  padding-bottom: 6px; }
.cardcol {
  width: var(--card); min-width: var(--card); max-width: var(--card);
}
body[data-density=compact] .cardcol {
  width: var(--card-compact); min-width: var(--card-compact); max-width: var(--card-compact);
}
.colhead {
  position: sticky; top: 0; background: var(--paper); padding: 6px 0 8px;
  border-bottom: 2px solid var(--rule); margin-bottom: 8px; z-index: 2;
}
.colhead b { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.colhead span { color: var(--quiet); font-size: 12px; }
.card {
  border: 1px solid var(--rule); border-radius: 4px; padding: 10px;
  margin-bottom: 8px; background: var(--panel);
}
.cardtop { display: flex; gap: 6px; flex-wrap: wrap; align-items: baseline;
  margin-bottom: 4px; }
.path { color: var(--quiet); font-size: 12px; margin-bottom: 4px; }
.badge {
  font-size: 11px; padding: 1px 6px; border-radius: 9px; border: 1px solid var(--rule);
  color: var(--quiet); background: var(--paper);
}
button.badge { cursor: pointer; }
.badge.derived { color: var(--derived); border-color: var(--derived); }
.fid { font-size: 11px; color: var(--quiet); margin-top: 6px; }
.riskbox { margin-top: 8px; border-left: 3px solid var(--risk); padding-left: 8px; }
.risklabel { font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--risk); }
.riskbox p { margin: 2px 0 0; }
details.panel { margin-top: 8px; }
details.panel > summary { cursor: pointer; font-size: 12px; color: var(--quiet); }
.panelbody { margin-top: 6px; font-size: 13px; }
.panelbody h5 { margin: 8px 0 2px; font-size: 12px; }
.panelbody pre { background: var(--band); padding: 6px; overflow-x: auto;
  border-radius: 3px; }

/* Landing page, chips, coverage strip, framework bar. */
.chips, .fwbar { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.intro { max-width: 760px; }
.introgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 8px; margin: 14px 0; }
.fwcard { border: 1px solid var(--rule); border-radius: 4px; padding: 9px;
  background: var(--panel); }
.fwcard b { display: block; }
.fwcard span { display: block; color: var(--quiet); font-size: 12px; }
.coverstrip { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.cover { border: 1px solid var(--rule); border-left-width: 3px; border-radius: 3px;
  padding: 4px 8px; font-size: 12px; background: var(--panel); }
.cover b { display: block; }
.cover span { color: var(--quiet); }
.cover.says { border-left-color: #2f7d55; }
.cover.silent { border-left-color: var(--rule); }
.cover.absent { border-left-color: var(--derived); background: var(--absent); }
.interp { margin-bottom: 10px; }
.terms { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 4px; }
.term { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: var(--mark-wide);
  color: var(--quiet); }
.term.core { background: var(--mark); color: var(--ink); }
.hidden-fw { display: none; }
section { margin-top: 22px; }
section h2 { font-size: 14px; margin: 0 0 6px; }
ul { margin: 0 0 10px; padding-left: 18px; }
li { margin-bottom: 4px; }
.note { color: var(--quiet); }
""" % {
    "pinned": PINNED,
    "comfortable": COMFORTABLE,
    "compact": COMPACT,
    "card": CARD_COMFORTABLE,
    "card_compact": CARD_COMPACT,
    "gap": COLUMN_GAP,
    "pad": PAGE_PADDING,
}

SCRIPT = """
(function () {
  var DENSITY = 'wacc-density', HIDDEN = 'wacc-hidden';

  function read(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(key, value); } catch (e) {}
  }

  function applyDensity(value) {
    document.body.dataset.density = value;
    document.querySelectorAll('[data-set-density]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.setDensity === value));
    });
  }
  applyDensity(read(DENSITY, 'comfortable'));
  document.querySelectorAll('[data-set-density]').forEach(function (button) {
    button.addEventListener('click', function () {
      applyDensity(button.dataset.setDensity);
      write(DENSITY, button.dataset.setDensity);
    });
  });

  // Hiding a framework is a reading preference, not a different question, so it stays on
  // the machine rather than in the URL. A key that is hidden but no longer on the page is
  // kept: it means this search did not reach that framework, not that the reader wants it
  // back.
  var hidden = {};
  read(HIDDEN, '').split(',').forEach(function (k) { if (k) hidden[k] = 1; });

  function applyHidden() {
    document.querySelectorAll('[data-fw]').forEach(function (node) {
      node.classList.toggle('hidden-fw', !!hidden[node.dataset.fw] && node.dataset.fw !== document.body.dataset.focusFw);
    });
    document.querySelectorAll('[data-toggle-fw]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(!hidden[button.dataset.toggleFw]));
    });
    write(HIDDEN, Object.keys(hidden).join(','));
  }
  document.querySelectorAll('[data-toggle-fw]').forEach(function (button) {
    button.addEventListener('click', function () {
      var key = button.dataset.toggleFw;
      if (hidden[key]) { delete hidden[key]; } else { hidden[key] = 1; }
      applyHidden();
    });
  });
  applyHidden();

  // Searching for a tag the publisher states is the quickest way to pull up everything
  // carrying it, and it is a search like any other, so it goes through the form.
  document.querySelectorAll('[data-search]').forEach(function (button) {
    button.addEventListener('click', function () {
      var box = document.getElementById('q');
      box.value = button.dataset.search;
      box.form.submit();
    });
  });

  // The panel is fetched from this server and nowhere else. It is HTML because the
  // escaping is done in Python, once, where the suite can read it.
  document.querySelectorAll('details[data-panel]').forEach(function (panel) {
    panel.addEventListener('toggle', function () {
      if (!panel.open || panel.dataset.loaded) { return; }
      panel.dataset.loaded = '1';
      var body = panel.querySelector('.panelbody');
      fetch('/control?uid=' + encodeURIComponent(panel.dataset.panel))
        .then(function (r) { return r.text(); })
        .then(function (t) { body.innerHTML = t; })
        .catch(function () { body.textContent = 'Could not load this panel.'; });
    });
  });

  if (document.body.dataset.focusFw) {
    var selectedPanel = document.querySelector('details[data-panel]');
    if (selectedPanel) selectedPanel.open = true;
  }

  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var was = button.textContent;
      button.textContent = 'Building...';
      fetch(button.dataset.copy)
        .then(function (r) { return r.text(); })
        .then(function (t) {
          return navigator.clipboard.writeText(t);
        })
        .then(function () { button.textContent = 'Copied'; })
        .catch(function () { button.textContent = 'Copy failed'; })
        .then(function () {
          setTimeout(function () { button.textContent = was; }, 1800);
        });
    });
  });
})();
"""


def esc(value: Optional[str]) -> str:
    return _html.escape(value or "", quote=True)


def _stems(subject: str) -> Tuple[List[str], List[str]]:
    """What the reader typed, and what a concept added on their behalf.

    Re-prepared from the subject rather than threaded through the analysis payload. It is
    a pure function of the query string and costs nothing, and the alternative is a
    parameter on every renderer that exists only so this line can be drawn.
    """
    prepared = prepare(subject or "")
    typed = list(prepared.stems) + list(prepared.alias_stems)
    return typed, list(prepared.concept_stems)


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


def _badges(control: Control) -> str:
    """The publisher's own tags, each a search for everything carrying it.

    Only the publisher's currency is offered this way. A tag this tool derived is not a
    set a reader can ask for, and offering it as one would present a derivation as though
    the publisher had drawn the boundary.
    """
    out = []
    for label, value in currency_of(control):
        for part in [p.strip() for p in value.split(",") if p.strip()]:
            out.append(
                '<button type="button" class="badge" data-search="%s" '
                'title="Search everything the publisher tags %s">%s</button>'
                % (esc(part), esc(label), esc(part))
            )
    return "".join(out[:6])


def _fidelity(corpus: Corpus, control: Control) -> str:
    """How this text got here. Half the corpus is transcribed from PDFs."""
    framework = corpus.frameworks.get(control.framework_key)
    value = control.fidelity or (framework.fidelity if framework else None)
    if value is None:
        return ""
    note = {
        Fidelity.OFFICIAL_MACHINE_READABLE:
            "from the publisher's own machine-readable release",
        Fidelity.STRUCTURED_EXTRACT:
            "transcribed from the published document — confirm before citing",
        Fidelity.CURATED_EXTRACT:
            "a curated extract of the published document — confirm before citing",
        Fidelity.PUBLISHER_IMPORT:
            "imported from the publisher's file on this machine",
        Fidelity.DERIVED: "derived by this tool",
    }.get(value, value.value)
    return '<div class="fid">%s</div>' % esc(note)


def _cell(corpus: Corpus, coverage, typed: Sequence[str], widened: Sequence[str]) -> str:
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
    for control in coverage.controls[:PER_FRAMEWORK]:
        body = " ".join((control.text or control.title or "").split())
        parts.append(
            '<div class="entry"><span class="ident">%s</span>'
            '<div class="states">%s</div>'
            '<div class="body">%s</div></div>'
            % (esc(control.identifier), _states(control), mark(body, typed, widened))
        )
    hidden = coverage.hidden + max(0, len(coverage.controls) - PER_FRAMEWORK)
    if hidden:
        parts.append('<div class="more">and %d more</div>' % hidden)
    return '<td class="col">%s</td>' % "".join(parts)


def _risk_block(statement: Optional[Statement]) -> str:
    """Show the complete risk scenario without a generated headline or appendix."""
    if statement is None:
        return ""
    return '<div class="riskbox"><span class="risklabel">Risk scenario</span><p>%s</p></div>' % esc(statement.text)


def _card(
    corpus: Corpus,
    control: Control,
    typed: Sequence[str],
    widened: Sequence[str],
    risk: Optional[Statement] = None,
    breadcrumb: Sequence[str] = (),
) -> str:
    framework = corpus.frameworks.get(control.framework_key)
    identifier = esc(control.identifier)
    if framework is not None and framework.source_url:
        # The framework's document, not the control's own anchor. No publisher in this
        # corpus gives a per-control URL, and inventing one would send a reader to a page
        # that does not exist.
        identifier = (
            '<a href="%s" target="_blank" rel="noopener" '
            'title="Open the %s document at its publisher">%s</a>'
            % (esc(framework.source_url), esc(framework.short_name), identifier)
        )
    parts = [
        '<div class="cardtop"><span class="ident">%s</span>%s</div>'
        % (identifier, _badges(control))
    ]
    trail = [c for c in breadcrumb if c and c != control.identifier]
    if trail:
        parts.append('<div class="path">%s</div>' % esc("  ›  ".join(trail)))
    if control.title and not control.title_is_shared and control.title != control.identifier:
        parts.append('<div class="path">%s</div>' % esc(control.title))
    parts.append('<div class="states">%s</div>' % _states(control))
    body = " ".join((control.text or control.title or "").split())
    parts.append('<div class="body">%s</div>' % mark(body, typed, widened))
    parts.append(_risk_block(risk))
    parts.append(
        '<details class="panel" data-panel="%s"><summary>Assessment and linked controls</summary>'
        '<div class="panelbody note">Loading…</div></details>'
        % esc(control.uid)
    )
    parts.append(_fidelity(corpus, control))
    return '<div class="card">%s</div>' % "".join(parts)


def _ordered_frameworks(analysis: Analysis) -> List:
    """Every framework the payload covers, in governance order, once each."""
    seen: List = []
    keys = set()
    for band in result_groups(analysis):
        for coverage in band.coverage:
            if coverage.framework.key not in keys:
                keys.add(coverage.framework.key)
                seen.append(coverage.framework)
    return seen


def _grid_view(
    corpus: Corpus, analysis: Analysis, frameworks: Sequence, typed, widened
) -> str:
    head = ['<th class="pin"><span>Results</span></th>']
    for framework in frameworks:
        head.append(
            '<th class="col" title="%s" data-fw="%s"><span>%s</span></th>'
            % (esc(framework.name), esc(framework.key), esc(framework.short_name))
        )

    rows = []
    for band in result_groups(analysis):
        by_key = {c.framework.key: c for c in band.coverage}
        cells = [
            '<td class="pin"><div>%s</div></td>' % esc(group_label(band))
        ]
        for framework in frameworks:
            coverage = by_key.get(framework.key)
            cell = (
                _cell(corpus, coverage, typed, widened)
                if coverage is not None
                else '<td class="col none">—</td>'
            )
            cells.append(cell.replace("<td ", '<td data-fw="%s" ' % esc(framework.key), 1))
        rows.append('<tr class="band">%s</tr>' % "".join(cells))

    return (
        '<div class="scroll"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>'
        % ("".join(head), "".join(rows))
    )


def _cards_view(
    corpus: Corpus,
    analysis: Analysis,
    frameworks: Sequence,
    typed,
    widened,
    risks: Optional[Dict[str, Statement]] = None,
    breadcrumbs: Optional[Dict[str, Sequence[str]]] = None,
) -> str:
    """One column per framework, tier bands collapsed.

    The tier is not lost, it is moved: a card names the band it came from only where the
    framework spans more than one, which is rare. Repeating 'Tier 4 — control catalogue'
    above every ISM control spends a line of every card on a fact the column header
    already carries.
    """
    risks = risks or {}
    breadcrumbs = breadcrumbs or {}
    columns = []
    for framework in frameworks:
        controls: List[Control] = []
        total = 0
        absent = ""
        for band in analysis.bands:
            for coverage in band.coverage:
                if coverage.framework.key != framework.key:
                    continue
                controls.extend(coverage.controls)
                total += coverage.total
                absent = absent or coverage.absent

        head = (
            '<div class="colhead"><b title="%s">%s</b><span>%s</span></div>'
            % (
                esc(framework.name),
                esc(framework.short_name),
                esc(
                    "not in this build" if absent
                    else "%d shown of %d read" % (len(controls), total) if controls
                    else "says nothing on this subject"
                ),
            )
        )
        if absent:
            body = ('<div class="card"><div class="note">Not in this build. %s</div>'
                    "</div>" % esc(absent))
        elif not controls:
            body = ('<div class="card"><div class="note">This framework is loaded and '
                    "says nothing on this subject.</div></div>")
        else:
            body = "".join(
                _card(
                    corpus, control, typed, widened,
                    risks.get(control.uid), breadcrumbs.get(control.uid, ()),
                )
                for control in controls
            )
        columns.append(
            '<div class="cardcol" data-fw="%s">%s%s</div>'
            % (esc(framework.key), head, body)
        )
    return '<div class="cards">%s</div>' % "".join(columns)


def _interpretation(subject: str) -> str:
    """How the query was read, and every term the search actually used.

    The reader is entitled to this before the results rather than after them. A control
    returned on a word nobody typed looks like a bug until the expansion is on screen,
    and scoring is in Python precisely so this can be shown.
    """
    if not subject:
        return ""
    prepared = prepare(subject)
    core = {s for s in prepared.stems} | {s for s in prepared.alias_stems}
    if prepared.concepts:
        lead = "Read as %s. Searched what you typed plus the wording each publisher " \
               "uses for it." % ", ".join(
                   c.key.replace("-", " ") for c in prepared.concepts
               )
    else:
        lead = ("No known subject matched this, so it was searched literally. "
                "Frameworks wording it differently will be missed.")
    chips = "".join(
        '<span class="term%s">%s</span>' % (" core" if stem in core else "", esc(stem))
        for stem in prepared.all_stems[:44]
    )
    more = len(prepared.all_stems) - 44
    if more > 0:
        chips += '<span class="term">and %d more</span>' % more
    return '<div class="interp"><div>%s</div><div class="terms">%s</div></div>' % (
        esc(lead), chips,
    )


def _coverage_strip(analysis: Analysis) -> str:
    """Which frameworks said something, which were silent, and which were not asked."""
    rows = []
    for framework in _ordered_frameworks(analysis):
        shown = total = 0
        absent = ""
        for band in analysis.bands:
            for coverage in band.coverage:
                if coverage.framework.key != framework.key:
                    continue
                shown += len(coverage.controls)
                total += coverage.total
                absent = absent or coverage.absent
        if absent:
            css, label = "absent", "not in this build"
        elif shown:
            css, label = "says", "%d shown of %d read" % (shown, total)
        else:
            css, label = "silent", "says nothing on this subject"
        rows.append(
            '<div class="cover %s" data-fw="%s"><b>%s</b><span>%s</span></div>'
            % (css, esc(framework.key), esc(framework.short_name), esc(label))
        )
    return '<div class="coverstrip">%s</div>' % "".join(rows)


def _framework_bar(analysis: Analysis) -> str:
    buttons = []
    for framework in _ordered_frameworks(analysis):
        shown = sum(
            len(c.controls) for b in analysis.bands for c in b.coverage
            if c.framework.key == framework.key
        )
        buttons.append(
            '<button type="button" class="badge" data-toggle-fw="%s" title="%s">'
            "%s (%d)</button>"
            % (esc(framework.key), esc(framework.name), esc(framework.short_name), shown)
        )
    return '<div class="fwbar">%s</div>' % "".join(buttons)


def _landing(corpus: Corpus) -> str:
    """What is loaded and what can be asked, before anything is asked.

    An empty search box is a question about the corpus, not about a subject, and a blank
    grid answers it with nothing. What loaded, under what licence and at what fidelity is
    the first thing a reader needs to judge anything the tool says afterwards.
    """
    cards = []
    for framework in corpus.frameworks.values():
        count = sum(
            1 for c in corpus.controls.values() if c.framework_key == framework.key
        )
        absent = corpus.absent_frameworks.get(framework.key, "")
        cards.append(
            '<div class="fwcard"><b>%s</b><span>%s</span><span>%s</span></div>'
            % (
                esc(framework.short_name),
                esc(" · ".join(x for x in (framework.publisher, framework.revision) if x)),
                esc(
                    "not in this build — %s" % absent if absent
                    else "%d controls · %s"
                    % (count, framework.fidelity.value if framework.fidelity else "")
                ),
            )
        )
    chips = "".join(
        '<button type="button" class="badge" data-search="%s">%s</button>'
        % (esc(concept.phrases[0]), esc(concept.key.replace("-", " ")))
        for concept in CONCEPTS[:18]
    )
    return (
        '<section class="intro"><h2>Find the same requirement in every framework at once</h2>'
        "<p>Search a subject and each framework is asked what it requires. The catalogues "
        "word the same control differently — the ISM says <em>patching</em>, the CSF "
        "says <em>vulnerabilities are identified</em>, C2M2 says <em>a vulnerability "
        "management activity is established</em> — so the search expands the wording "
        "and shows every term it used.</p>"
        '<div class="chips">%s</div>'
        '<div class="introgrid">%s</div>'
        '<p class="note">Everything runs on this machine against the corpus already on '
        "disk. Nothing is sent anywhere.</p></section>"
        % (chips, "".join(cards))
    )


def _sections(corpus: Corpus, analysis: Analysis) -> str:
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
            '<p class="note">These frameworks are registered and were not loaded, so '
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
    return "".join(sections)


def _toolbar(subject: str, view: str, limit: int) -> str:
    url_query = urllib.parse.quote(subject or "", safe="")
    other = "cards" if view == "grid" else "grid"
    options = "".join(
        '<option value="%d"%s>%d per framework</option>'
        % (n, " selected" if n == limit else "", n)
        for n in LIMIT_CHOICES
    )
    return (
        '<form method="get" action="/">'
        '<input type="search" id="q" name="q" value="%(query)s" '
        'placeholder="a subject, or a control identifier" autofocus>'
        '<input type="hidden" name="view" value="%(view)s">'
        '<button type="submit">Search</button>'
        '<select name="limit" onchange="this.form.submit()">%(options)s</select>'
        '<a class="btn" href="/?q=%(url)s&amp;view=%(other)s&amp;limit=%(limit)d">'
        "Show as %(other)s</a>"
        '<button type="button" data-set-density="comfortable">Comfortable</button>'
        '<button type="button" data-set-density="compact">Compact</button>'
        '<a class="btn" href="/export.csv?q=%(url)s">CSV</a>'
        '<a class="btn" href="/export.md?q=%(url)s">Markdown</a>'
        '<button type="button" data-copy="/exec.md?q=%(url)s">Copy risk summary</button>'
        '<button type="button" data-copy="/plan.md?q=%(url)s">Copy test plan</button>'
        "</form>"
        % {
            "query": esc(subject),
            "view": esc(view),
            "other": esc(other),
            "url": url_query,
            "limit": limit,
            "options": options,
        }
    )


def render(
    corpus: Corpus,
    analysis: Analysis,
    title: str = "WA Control Crosswalk",
    view: str = "grid",
    limit: int = 25,
    risks: Optional[Dict[str, Statement]] = None,
    breadcrumbs: Optional[Dict[str, Sequence[str]]] = None,
) -> str:
    view = "cards" if view == "cards" else "grid"
    typed, widened = _stems(analysis.subject)
    focused = corpus.control(analysis.subject)
    if focused is not None:
        typed, widened = [], []
    frameworks = ([corpus.frameworks[focused.framework_key]] if focused is not None
                  else _ordered_frameworks(analysis))

    if not (analysis.subject or "").strip():
        main = _landing(corpus)
        furniture = ""
    else:
        furniture = ("" if focused is not None else
                     _interpretation(analysis.subject) + _coverage_strip(analysis)
                     + _framework_bar(analysis))
        main = (
            _cards_view(corpus, analysis, frameworks, typed, widened, risks, breadcrumbs)
            if view == "cards"
            else _grid_view(corpus, analysis, frameworks, typed, widened)
        )

    speaking = sum(1 for b in analysis.bands for c in b.coverage if c.total)
    missing = len(analysis.frameworks_absent)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>%(title)s</title><style>%(style)s</style></head>"
        '<body data-density="comfortable" data-focus-fw="%(focus_fw)s">'
        '<p><a href="/library">← Control workspace</a></p>'
        "<h1>%(title)s</h1>"
        '<div class="sub">%(sub)s</div>'
        "%(toolbar)s%(furniture)s%(main)s%(sections)s"
        "<script>%(script)s</script></body></html>"
        % {
            "focus_fw": esc(focused.framework_key if focused is not None else ""),
            "title": esc(title),
            "style": STYLE,
            "sub": esc(
                "%d controls across %d frameworks on this machine"
                % (len(corpus.controls), analysis.frameworks_present)
                if not (analysis.subject or "").strip()
                else "%s — %d controls shown of %d read, across %d of %d frameworks "
                "in this build%s"
                % (
                    analysis.subject,
                    len(analysis.controls),
                    analysis.depth,
                    speaking,
                    analysis.frameworks_present,
                    " · %d of %d registered frameworks are not in this build"
                    % (missing, len(corpus.frameworks)) if missing else "",
                )
            ),
            "toolbar": _toolbar(analysis.subject, view, limit),
            "furniture": furniture,
            "main": main,
            "sections": _sections(corpus, analysis) if (analysis.subject or "").strip() else "",
            "script": SCRIPT,
        }
    )


def control_panel(corpus: Corpus, derivation, placement=None, lineage=None) -> str:
    """The fragment under one control: how to test it, what it links to, where it sits.

    Published material first and named as its publisher's. NIST writes the 800-53A
    assessment objectives and this tool does not, so presenting them unattributed beside a
    derived procedure would put NIST's name behind a sentence NIST never wrote.
    """
    control = derivation.control
    parts: List[str] = []

    if derivation.refusal is not None:
        parts.append(
            '<p class="note">No test derived. %s — %s</p>'
            % (esc(derivation.refusal.reason), esc(derivation.refusal.detail))
        )

    if placement is not None and placement.needs_its_parent:
        parts.append(
            '<p class="note">Quoting this alone would misrepresent it. It continues '
            "a sentence that begins in %s.</p>"
            % esc(", ".join(c.identifier for c in placement.stem_parts))
        )

    for material in derivation.related_assessments:
        source = material.control
        link = "/?" + urllib.parse.urlencode({"q": source.uid, "view": "cards"})
        name = "%s %s — %s" % (corpus.frameworks[source.framework_key].short_name,
                                 source.identifier, source.title or "Assessment material")
        parts.append('<details class="panel"><summary>Related assessment: '
                     '<a href="%s">%s</a></summary><div class="panelbody">'
                     '<p class="note">Connection: %s. %s</p>' %
                     (esc(link), esc(name), esc(material.connection.value), esc(material.basis)))
        for statement in material.statements:
            parts.append('<h5>%s</h5><p>%s</p>' % (
                esc(statement.published_by or "Publisher"),
                esc(statement.text).replace("\n", "<br>")))
        parts.append('</div></details>')

    for statement in derivation.published:
        parts.append("<h5>Published procedure — %s</h5><p>%s</p>" % (
            esc(statement.published_by or "the publisher"), esc(statement.text).replace("\n", "<br>"),
        ))

    for statement in derivation.derived_tests:
        label = "Suggested assessment"
        parts.append("<h5>%s</h5><p>%s</p>" % (esc(label), esc(statement.text)))

    if derivation.detail:
        titles = {str(s["key"]): str(s["title"]) for s in _detail_sources()}
        rows = "".join(
            "<li><strong>%s %s</strong> — %s<br><span class=\"note\">%s</span></li>"
            % (
                esc(titles.get(d.source_key, d.source_key)),
                esc(d.identifier),
                esc(d.title),
                esc(d.platform),
            )
            for d in derivation.detail[:6]
        )
        parts.append(
            "<h5>Product detail</h5><ul>%s</ul>"
            '<p class="note">CIS benchmark text, import-only, and never this control’s '
            "own requirement. Whether the product is in scope here is your call.</p>" % rows
        )

    if lineage is not None and lineage.has_anything:
        for band in lineage.bands:
            if band.is_empty:
                continue
            rows = "".join(
                '<li><a href="%s"><strong>%s %s</strong></a> — %s<br>'
                '<span class="note">%s</span></li>'
                % (
                    esc("/?" + urllib.parse.urlencode({"q": r.other.uid, "view": "cards"})),
                    esc(corpus.frameworks[r.other.framework_key].short_name),
                    esc(r.other.identifier),
                    esc(r.link.kind.value if hasattr(r.link.kind, "value") else r.link.kind),
                    esc(r.direction_note(corpus)),
                )
                for r in band.relations
            )
            parts.append(
                "<h5>Linked — %s</h5><ul>%s</ul>%s"
                % (
                    esc(band.provenance.value),
                    rows,
                    '<p class="note">%s</p>' % esc(band.note) if band.note else "",
                )
            )

    if not parts:
        parts.append('<p class="note">Nothing further on this control.</p>')
    return "".join(parts)


def _detail_sources():
    from ..registry import DETAIL_SOURCES

    return DETAIL_SOURCES
