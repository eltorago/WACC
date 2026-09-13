"""Renderers. All three read the analysis payload and none of them recomputes it.

One payload, three renderers, because the alternative is three places where a coverage
figure can disagree with itself. If a renderer needs something the payload does not carry,
the payload is what changes.
"""

