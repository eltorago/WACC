"""CISA's Zero Trust Maturity Model, one control per function.

The document states what an agency looks like at each of four maturity stages rather than
what it must do, which is the same shape as the AESCSF's maturity indicator levels and the
reason this sits at tier 3 rather than in a catalogue.

One row per function, not one per function-stage. Four near-identical rows per function
would fill every result set with descriptors of the same thing; the stages are carried as
publisher tags so a reader can still see the progression and a renderer can still show it.

Identifiers are generated, because the document numbers nothing. They are the pillar and
the function name, which is what the document itself uses to refer to a row, and they are
stable as long as the names are.
"""

import json
import os
from typing import List

from ..model import (
    Control,
    Corpus,
    Framework,
    ObligationStrength,
    Origin,
    Provenance,
)

STAGES = ("Traditional", "Initial", "Advanced", "Optimal")


def load(corpus: Corpus, framework: Framework, path: str, verbose: bool = False) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    functions = payload.get("functions", [])
    if not functions:
        corpus.load_warnings.append("ztmm: extract is empty; nothing loaded")
        return 0

    pillars: List[str] = []
    for record in functions:
        pillar = record.get("pillar") or "Unattributed"
        if pillar not in pillars:
            pillars.append(pillar)
            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    identifier=pillar,
                    text="",
                    title=pillar,
                    depth=0,
                    obligation=ObligationStrength.INFORMATIVE,
                    obligation_provenance=Provenance.PUBLISHED,
                    attributes={"structural": True},
                    origin=Origin.GENERATED,
                )
            )

    loaded = 0
    for record in functions:
        pillar = record.get("pillar") or "Unattributed"
        name = record["name"]
        stages = record.get("stages", {})
        # The control text is what the document says, which is the progression itself.
        # Picking one stage as the text would assert that CISA requires that stage, and
        # it does not: the model describes where an agency is, not where it must be.
        body = " ".join(
            "%s: %s" % (stage, stages.get(stage, "").strip())
            for stage in STAGES
            if stages.get(stage, "").strip()
        )
        tags = {"maturity_stages": [s for s in STAGES if stages.get(s, "").strip()]}
        for stage in STAGES:
            value = stages.get(stage, "").strip()
            if value:
                tags["stage_%s" % stage.lower()] = value
        if record.get("note"):
            tags["revision_note"] = record["note"]

        corpus.add_control(
            Control(
                framework_key=framework.key,
                identifier="%s/%s" % (pillar, name),
                text=body,
                title=name,
                depth=1,
                parent_uid="%s:%s" % (framework.key, _key(pillar)),
                obligation=ObligationStrength.UNKNOWN,
                obligation_provenance=Provenance.PUBLISHED,
                publisher_tags=tags,
                section_ref=pillar,
                origin=Origin.GENERATED,
            )
        )
        loaded += 1

    if verbose:
        print("  ZTMM: %d functions across %d pillars" % (loaded, len(pillars)))
    return loaded


def _key(value: str) -> str:
    from ..model import normalise_identifier

    return normalise_identifier(value)
