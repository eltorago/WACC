"""Column arithmetic for the results grid, kept where it can be tested.

The grid is a crosswalk: the pinned left column names the tier band, each remaining column
is a framework in governance order, and a cell holds what that framework says about the
subject. So the only layout question that matters is how many frameworks a reader can see
at once, and that is arithmetic rather than a matter of taste.

Columns are sized in pixels, never in vw. A vw column changes width with the window, so
the number of columns never changes and the text inside them reflows instead: at 1366 the
reader gets three cramped columns and at 2560 three wide ones, which is the opposite of
what more screen is for. Fixed widths mean more screen buys more frameworks.

Both densities are here because they answer different questions. Comfortable shows the
control text, for reading one requirement properly. Compact shows the identifier, the
obligation strength, the publisher's tags and two clamped lines, for seeing how far a
subject reaches across sixteen documents at once.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Fixed pixel widths. The brief's figures, and the reason they are not vw is above.
COMFORTABLE = 320
COMPACT = 208

# The pinned column holds the tier band label and its question. It is the same width in
# both densities, because the label does not get shorter when the data does.
PINNED = 200

# Grid furniture: the outer page padding plus one column gap per column.
PAGE_PADDING = 24
COLUMN_GAP = 8

# The widths to measure at. Not a preference — these are the three monitors an entity
# actually has, and a layout change is checked against all three before and after.
MEASURED_WIDTHS = (1366, 1920, 2560)

# Measured before and after the one layout change made so far, which was narrowing the
# pinned column from 220 to 200 and the gap from 12 to 8.
#
#                    before (220/12)      after (200/8)
#   1366 comfortable   3  (+102 px)        3  (+134 px)
#   1366 compact       4  (+218 px)        5  (+38 px)
#   1920 comfortable   4  (+324 px)        5  (+32 px)
#   1920 compact       7  (+112 px)        7  (+160 px)
#   2560 comfortable   6  (+300 px)        7  (+16 px)
#   2560 compact      10  (+92 px)        10  (+152 px)
#
# Three widths gained a column and none lost one. The 218 px left over at 1366 compact was
# most of an unused column, which is what prompted the change. Sixteen frameworks never all
# fit, which is why the left column pins and the grid scrolls sideways.
EXPECTED_COLUMNS = {
    (1366, "comfortable"): 3,
    (1366, "compact"): 5,
    (1920, "comfortable"): 5,
    (1920, "compact"): 7,
    (2560, "comfortable"): 7,
    (2560, "compact"): 10,
}

DENSITIES: Dict[str, int] = {"comfortable": COMFORTABLE, "compact": COMPACT}


@dataclass
class Fit:
    width: int
    density: str
    column_width: int
    columns: int
    leftover: int

    def describe(self) -> str:
        return "%d px, %s: %d framework columns beside the pinned one, %d px left over" % (
            self.width,
            self.density,
            self.columns,
            self.leftover,
        )


def columns_at(width: int, density: str, pinned: bool = True) -> Fit:
    """How many framework columns fit, given a viewport width."""
    column_width = DENSITIES[density]
    available = width - PAGE_PADDING * 2
    if pinned:
        available -= PINNED + COLUMN_GAP
    if available <= 0:
        return Fit(width, density, column_width, 0, max(0, available))
    # Each column carries its own trailing gap except the last.
    columns = (available + COLUMN_GAP) // (column_width + COLUMN_GAP)
    used = columns * column_width + max(0, columns - 1) * COLUMN_GAP
    return Fit(width, density, column_width, int(columns), int(available - used))


def measure(pinned: bool = True) -> List[Fit]:
    """Every width and density, for the record that a layout change is checked against."""
    return [
        columns_at(width, density, pinned)
        for width in MEASURED_WIDTHS
        for density in ("comfortable", "compact")
    ]


def table() -> str:
    lines = ["width   density        columns  leftover"]
    for fit in measure():
        lines.append(
            "%-7d %-14s %7d  %8d" % (fit.width, fit.density, fit.columns, fit.leftover)
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(table())
