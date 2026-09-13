"""C2M2, loaded at three granularities: domain, objective, practice.

The model states capability rather than obligation — "IT and OT assets that are important
to the delivery of the function are inventoried, at least in an ad hoc manner" is a
description of a state an organisation is in, not an instruction. That is the same shape
as the AESCSF's maturity indicator levels, and it is why C2M2 sits at tier 3 rather than
in a catalogue.

The maturity indicator level is the publisher's own currency and is carried as a tag, not
folded into an obligation strength. It is also the operative half of what the CIRMP Rules
require: s 8(4) names C2M2 at MIL1 and s 8A(3) names Version 2.1 at MIL2, so a practice
without its level cannot be read against either provision.

Identifiers are the document's own. C2M2 refers to its practices as ARCHITECTURE-1f in
running text, which is the domain short name, the objective number and the practice
letter, and that is what is generated here.
"""

import json
from typing import Dict, List

from ..model import (
    Control,
    Corpus,
    Framework,
    ObligationStrength,
    Origin,
    Provenance,
)


def load(corpus: Corpus, framework: Framework, path: str, verbose: bool = False) -> int:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    practices = payload.get("practices", [])
    if not practices:
        corpus.load_warnings.append("c2m2: extract is empty; nothing loaded")
        return 0

    stated = payload.get("stated_practices")
    if stated and len(practices) != stated:
        # The document states its own totals in section 4.1. A mismatch means the extract
        # is of something else, and it is worth saying so in the build rather than in a
        # result set.
        corpus.load_warnings.append(
            "c2m2: extract holds %d practices; the document states %d"
            % (len(practices), stated)
        )

    domains: List[str] = []
    objectives: Dict[str, str] = {}
    loaded = 0

    for record in practices:
        domain = str(record["domain"])
        number = int(record["objective_number"])
        objective_uid = "%s:%s-%d" % (framework.key, domain.lower(), number)

        if domain not in domains:
            domains.append(domain)
            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    identifier=domain,
                    text="",
                    title=domain,
                    depth=0,
                    obligation=ObligationStrength.INFORMATIVE,
                    obligation_provenance=Provenance.PUBLISHED,
                    attributes={"structural": True},
                    origin=Origin.GENERATED,
                )
            )

        if objective_uid not in objectives:
            objectives[objective_uid] = str(record["objective"])
            corpus.add_control(
                Control(
                    framework_key=framework.key,
                    identifier="%s-%d" % (domain, number),
                    text="",
                    title=str(record["objective"]),
                    depth=1,
                    parent_uid="%s:%s" % (framework.key, domain.lower()),
                    obligation=ObligationStrength.INFORMATIVE,
                    obligation_provenance=Provenance.PUBLISHED,
                    attributes={"structural": True},
                    section_ref=domain,
                    origin=Origin.GENERATED,
                )
            )

        tags: Dict[str, object] = {}
        if record.get("mil"):
            tags["maturity_indicator_level"] = "MIL%d" % int(record["mil"])

        corpus.add_control(
            Control(
                framework_key=framework.key,
                identifier=str(record["identifier"]),
                text=str(record["text"]),
                title=None,
                depth=2,
                parent_uid=objective_uid,
                obligation=ObligationStrength.UNKNOWN,
                obligation_provenance=Provenance.PUBLISHED,
                publisher_tags=tags,
                section_ref="%s %s" % (domain, record["objective"]),
                origin=Origin.SHIPPED,
            )
        )
        loaded += 1

    if verbose:
        print(
            "  C2M2: %d practices across %d objectives in %d domains"
            % (loaded, len(objectives), len(domains))
        )
    return loaded
