"""MITRE ATT&CK Enterprise, loaded as a threat layer beside the control spine.

ATT&CK is not a control framework and nothing here places it in a tier. A technique
states what an adversary does and a control states what an entity must do; the five-tier
spine orders documents by how much authority they carry over an entity, and a threat
taxonomy has none. It is loaded because knowing which techniques a control blunts is
what turns 'this control is absent' into a statement about exposure.

MITRE's own 'mitigates' edges between its mitigations and its techniques are published
and load as such. Nothing in this file connects ATT&CK to the ISM, the PSPF or any other
document in the corpus, because MITRE publishes no such mapping in this export. Any link
from a mitigation to a control is this tool matching on subject, and is derived on demand
rather than stored.
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from ..io.xlsx import Workbook
from ..model import (
    Corpus,
    Licence,
    Mitigates,
    Mitigation,
    Provenance,
    Technique,
    ThreatSource,
)

SOURCE_KEY = "attack-enterprise"

# ATT&CK is published by MITRE for free use with attribution, but this export states no
# terms anywhere in it and the build machine has no egress to check MITRE's site. Held
# import-only until the terms are read off the source, so the packaging test cannot ship
# text whose licence nobody in this build has actually seen.
LICENCE_NOTE = (
    "Held import-only pending confirmation. The workbook states no terms and the licence "
    "was not read from a source document during this build. Flip to shippable only after "
    "reading MITRE's terms of use; the packaging test enforces this either way."
)


def _split(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def load(corpus: Corpus, path: str, verbose: bool = False) -> int:
    book = Workbook(path)
    names = set(book.sheet_names)
    for needed in ("techniques", "mitigations", "relationships"):
        if needed not in names:
            corpus.load_warnings.append(
                "ATT&CK workbook has no %r sheet; threat layer not loaded" % needed
            )
            return 0

    techniques = _rows(book, "techniques")
    mitigations = _rows(book, "mitigations")
    relationships = _rows(book, "relationships")
    version, created = _version_of(path)
    if version == "unstated":
        corpus.load_warnings.append(
            "ATT&CK export states no version anywhere in the workbook and the "
            "file name does not carry one; recorded as unstated rather than guessed"
        )
    corpus.threat_sources[SOURCE_KEY] = ThreatSource(
        key=SOURCE_KEY,
        title="MITRE ATT&CK Enterprise",
        publisher="MITRE",
        version=version,
        retrieved=created,
        licence=Licence.IMPORT_ONLY,
        licence_note=LICENCE_NOTE,
        source_file=path.rsplit("/", 1)[-1],
    )

    loaded = 0
    for row in techniques:
        key = (row.get("ID") or "").strip()
        if not key:
            continue
        corpus.add_technique(
            Technique(
                key=key,
                name=(row.get("name") or "").strip(),
                description=(row.get("description") or "").strip(),
                tactics=_split(row.get("tactics")),
                platforms=_split(row.get("platforms")),
                is_sub_technique=str(row.get("is sub-technique")).strip().lower()
                in ("true", "1", "yes"),
                parent_key=(row.get("sub-technique of") or "").strip() or None,
                url=(row.get("url") or "").strip() or None,
                version=str(row.get("version") or "").strip() or None,
            )
        )
        loaded += 1

    for row in mitigations:
        key = (row.get("ID") or "").strip()
        if not key:
            continue
        corpus.add_mitigation(
            Mitigation(
                key=key,
                name=(row.get("name") or "").strip(),
                description=(row.get("description") or "").strip(),
                url=(row.get("url") or "").strip() or None,
                version=str(row.get("version") or "").strip() or None,
            )
        )
        loaded += 1

    edges = 0
    for row in relationships:
        if (row.get("mapping type") or "").strip().lower() != "mitigates":
            continue
        if (row.get("source type") or "").strip().lower() != "mitigation":
            continue
        corpus.add_mitigates(
            Mitigates(
                mitigation_key=(row.get("source ID") or "").strip(),
                technique_key=(row.get("target ID") or "").strip(),
                provenance=Provenance.PUBLISHED,
                asserted_by="MITRE",
                basis="ATT&CK Enterprise %s relationship of type 'mitigates'" % version,
            )
        )
        edges += 1

    if verbose:
        print(
            "  ATT&CK Enterprise %s: %d techniques, %d mitigations, %d mitigates edges"
            % (version, len(corpus.techniques), len(corpus.mitigations), len(corpus.mitigates))
        )
    return loaded + edges


def _rows(book: Workbook, sheet: str) -> List[Dict[str, str]]:
    """Rows keyed by the sheet's own header, so a column move is a miss not a shift."""
    header, body = book.table(sheet)
    return [dict(zip(header, row)) for row in body]


_VERSION_IN_NAME = re.compile(r"v(\d+(?:\.\d+)*)", re.I)


def _version_of(path: str) -> Tuple[str, Optional[str]]:
    """The export's version and build date, read off the file rather than remembered.

    The workbook carries no version anywhere in its data: the 'version' column on the
    techniques sheet is that technique's own revision, and 'domain' is the matrix name,
    not the release. The first attempt read 'domain' and recorded every ATT&CK release as
    'enterprise-attack'. So the release comes from the file name, which is where MITRE
    puts it, and the build date comes from the package properties, which is stated.
    """
    name = os.path.basename(path)
    match = _VERSION_IN_NAME.search(name)
    version = match.group(1) if match else "unstated"

    created = None
    try:
        with zipfile.ZipFile(path) as bundle:
            root = ET.fromstring(bundle.read("docProps/core.xml"))
            for element in root.iter():
                if element.tag.endswith("}created") and element.text:
                    created = element.text.strip()
                    break
    except (KeyError, zipfile.BadZipFile, ET.ParseError):
        created = None
    return version, created
