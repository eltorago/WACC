"""CIS benchmark recommendations, loaded as detail rather than as controls.

A benchmark states how to configure one product. It is not a framework column and it has
no tier: 'Ensure Ephemeral profile is set to Disabled' is not a peer of an ISM control, it
is one way to carry out part of one. So these load into their own collection and reach a
reader only inside a test procedure for the control they harden.

CIS text is import-only. Nothing here may be shipped, and the packaging check is what
enforces that.
"""

import json
import os
from typing import Dict, List

from ..model import Corpus, Detail, Licence
from ..registry import DETAIL_SOURCES


def load(corpus: Corpus, directory: str, verbose: bool = False) -> int:
    loaded = 0
    for source in DETAIL_SOURCES:
        key = str(source["key"])
        path = os.path.join(directory, "%s.json" % key)
        if not os.path.exists(path):
            corpus.load_warnings.append(
                "benchmark detail for %s not extracted; run tools/extract_cis_benchmark.py"
                % key
            )
            continue
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)

        platform = payload.get("platform") or str(source.get("platform", ""))
        for record in payload.get("recommendations", []):
            body = record.get("description") or ""
            rationale = record.get("rationale") or ""
            corpus.add_detail(
                Detail(
                    source_key=key,
                    identifier=record["identifier"],
                    title=record["title"],
                    text=(body + (" " + rationale if rationale else "")).strip(),
                    platform=platform,
                    profile_levels=record.get("profile_levels", []),
                    audit=record.get("audit") or None,
                    remediation=record.get("remediation") or None,
                    default_value=record.get("default_value") or None,
                    publisher_tags={"assessment": record.get("assessment", "")},
                    licence=Licence.IMPORT_ONLY,
                )
            )
            loaded += 1

        expected = int(source.get("expected") or 0)
        count = len(payload.get("recommendations", []))
        if expected and count != expected:
            corpus.load_warnings.append(
                "%s extracted %d recommendations, registry expects %d"
                % (key, count, expected)
            )
        if verbose:
            print("  %-12s %4d recommendations (%s)" % (key, count, platform))
    return loaded
