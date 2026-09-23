"""Adapter for the existing WA policy extract and versioned pilot rule data."""
import json
import os
from pathlib import Path
from .contracts import PolicyError, fingerprint
from .rules import validate_rule

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CORPUS_VERSION = "2026.09.23-pilot.2"
REVIEW_FRAMEWORKS = {"wa-csp": "WA CSP", "ism": "ASD ISM", "aescsf": "AESCSF"}
MANUAL_FRAMEWORKS = ("ism", "aescsf", "essential-eight", "csf")


def training_rules():
    return json.loads((DATA / 'policy/pilot-rules.json').read_text(encoding='utf-8'))['rules']


def _wa_requirements(edition=None):
    path = Path(os.environ.get("WACC_LIBRARY", str(ROOT))) / "data/corpus/wa-csp.json"
    if not path.is_file():
        raise PolicyError("The locally permitted WA CSP extract is missing. Configure WACC_LIBRARY to the source repository; no download is attempted.", 5)
    raw = path.read_bytes()
    if len(raw) > 4 * 1024 * 1024:
        raise PolicyError("Baseline exceeds the supported corpus limit.", 5)
    data = json.loads(raw)
    title = data["title"]
    if edition and edition != title:
        raise PolicyError("Requested framework edition is not installed. Use wacc frameworks.", 5)
    import hashlib
    pilot = json.loads((DATA / 'policy/pilot-rules.json').read_text(encoding='utf-8'))
    if hashlib.sha256(raw).hexdigest() != pilot['sourceExtractHash'] or title != pilot['frameworkEdition']:
        raise PolicyError('The local WA extract differs from the edition pinned to these pilot rules. Review and version it before analysis.', 5)
    source_meta = dict(id="wa-csp", title=title, edition=title, sourceFile=data["source_file"],
                       extractHash=hashlib.sha256(raw).hexdigest(),
                       sourceUri="https://www.wa.gov.au/government/publications/2024-wa-government-cyber-security-policy",
                       licence="Local import only; do not redistribute this snapshot without permission.")
    permissions = ROOT / "sources/permissions.json"
    if permissions.is_file():
        entry = next((f for f in json.loads(permissions.read_text(encoding="utf-8"))["files"] if f["filename"] == data["source_file"]), {})
        source_meta["sourceHash"] = entry.get("sha256")
    requirements = []
    for record in data["records"]:
        uid = "wa-csp:" + record["identifier"]
        obligations = training_rules() if record["identifier"] == "3.2a" else [dict(id="WACC-" + uid, interpretation=record["text"], rule=None)]
        for atom in obligations:
            atom.update(mandatory=True, ruleVersion="1.0", assessmentMethod="DocumentReview",
                        reviewStatus="DraftNeedsHumanReview" if atom["rule"] else "ManualReviewOnly",
                        provenance="WACC interpretation; not publisher wording")
            if atom["rule"]:
                validate_rule(atom["rule"])
        requirements.append(dict(id=uid, frameworkId="wa-csp", officialReference=record["identifier"],
                                 heading=record["section_title"], parentId=record["section_number"],
                                 authoritativeText=record["text"], context=record.get("lead_in", ""),
                                 sourceLocator=dict(section=record["section_number"], reference=record["identifier"]),
                                 obligations=obligations))
    return source_meta, requirements


def _library(keys=MANUAL_FRAMEWORKS):
    from ..build import build
    library_root = Path(os.environ.get('WACC_LIBRARY', str(ROOT)))
    return build(False, source_root=library_root/'sources/files', corpus_root=library_root/'data/corpus', framework_keys=keys)[0]


def _controls(existing, key):
    # AESCSF domains and objectives are headings; count its practices once.
    return [c for c in existing.controls_for(key) if c.text and not c.attributes.get('structural')
            and (key != 'aescsf' or c.depth == 2)]


def _imported_rows(packet):
    pilot = json.loads((DATA/'policy/pilot-rules.json').read_text(encoding='utf-8'))
    rows = []
    for source in packet['requirements']:
        row = {key:source[key] for key in ('id','frameworkId','officialReference','heading','parentId','authoritativeText','context','sourceLocator')}
        trusted_training = (row['id'] == 'wa-csp:3.2a' and packet['framework']['sourceHash'] == pilot.get('reviewedSourceHash')
                            and fingerprint([row['authoritativeText'],row['context']]) == pilot.get('trainingRequirementHash'))
        atoms = training_rules() if trusted_training else [dict(id='WACC-' + row['id'],interpretation=row['authoritativeText'],rule=None)]
        for atom in atoms:
            atom.update(mandatory=True,ruleVersion='1.0',assessmentMethod='DocumentReview',
                        reviewStatus='DraftNeedsHumanReview' if atom['rule'] else 'ManualReviewOnly',
                        provenance='WACC interpretation; source imported locally')
            if atom['rule']: validate_rule(atom['rule'])
        row['obligations'] = atoms
        rows.append(row)
    return rows


def load(framework="wa-csp", edition=None, corpus_version=None, also=()):
    selected = list(dict.fromkeys([framework, *also]))
    local_version = bool(corpus_version and corpus_version.startswith(CORPUS_VERSION + '-local-'))
    if corpus_version and corpus_version != CORPUS_VERSION and not local_version:
        from .packages import installed
        packaged = installed(corpus_version)
        if not set(selected) <= {f['id'] for f in packaged['frameworks']}:
            raise PolicyError("Selected framework is absent from the corpus package.", 5)
        if edition and not any(f['id'] == framework and f['edition'] == edition for f in packaged['frameworks']):
            raise PolicyError("Requested edition is absent from the corpus package.", 5)
        packaged['requirements'] = [r for r in packaged['requirements'] if r['frameworkId'] in selected]
        packaged['frameworks'] = [f for f in packaged['frameworks'] if f['id'] in selected]
        ids = {r['id'] for r in packaged['requirements']}
        packaged['mappings'] = [m for m in packaged['mappings'] if m['source'] in ids and m['target'] in ids]
        return packaged
    if not set(selected) <= {'wa-csp', *MANUAL_FRAMEWORKS}:
        raise PolicyError('Unsupported assessment framework. Use wacc frameworks to see the available choices.', 5)
    requirements, frameworks, mappings = [], [], []
    from . import updates
    imported = {key:updates.current(key) for key in selected if key in REVIEW_FRAMEWORKS} if corpus_version != CORPUS_VERSION else {}
    imported = {key:value for key,value in imported.items() if value is not None}
    version = CORPUS_VERSION + (updates.version_suffix() if corpus_version != CORPUS_VERSION else '')
    if local_version and corpus_version != version:
        raise PolicyError('Requested local corpus version is no longer active. Open its saved assessment to inspect historical results.', 5)
    for key, packet in imported.items():
        if key == framework and edition and edition != packet['framework']['edition']:
            raise PolicyError('Requested framework edition is not active.', 5)
        frameworks.append(packet['framework'])
        requirements.extend(_imported_rows(packet))
        mappings.extend(packet['mappings'])
    if 'wa-csp' in selected and 'wa-csp' not in imported:
        metadata, wa_rows = _wa_requirements(edition if framework == 'wa-csp' else None)
        frameworks.append(metadata)
        requirements.extend(wa_rows)
    manual = [key for key in selected if key in MANUAL_FRAMEWORKS and key not in imported]
    if manual:
        existing = _library(selected)
        for key in manual:
            fw = existing.frameworks[key]
            controls = _controls(existing, key)
            if not controls:
                raise PolicyError('Selected framework is unavailable locally: ' + key + '. Prepare its local sources before analysis.', 5)
            if key == framework and edition and edition != fw.revision:
                raise PolicyError('Requested framework edition is not installed. Use wacc frameworks.', 5)
            frameworks.append(dict(id=key, title=fw.name, edition=fw.revision, sourceFile=fw.source_file, sourceUri=fw.source_url,
                                   extractHash=fingerprint([(c.uid, c.text, c.section_ref, c.attributes, c.publisher_tags) for c in controls]), licence=fw.licence.value))
            for c in controls:
                parent = existing.controls.get(c.parent_uid)
                requirements.append(dict(id=c.uid, frameworkId=key, officialReference=c.identifier,
                                         heading=c.title or c.section_ref or "", parentId=c.parent_uid,
                                         authoritativeText=c.text, context=(parent.text if key == 'aescsf' and parent else c.attributes.get("lead_in", "")),
                                         sourceLocator=dict(reference=c.identifier),
                                         obligations=[dict(id="WACC-" + c.uid, interpretation=c.text, rule=None,
                                                           mandatory=True, ruleVersion="1.0", assessmentMethod="ManualReview",
                                                           reviewStatus="ManualReviewOnly", provenance="Source imported; decomposition pending")]))
        selected_ids = {r["id"] for r in requirements}
        for link in existing.links:
            if link.source_uid in selected_ids and link.target_uid in selected_ids:
                mappings.append(dict(source=link.source_uid, target=link.target_uid, relationship="RelatedTo",
                                     relation="MappedOnly", provenance=str(link.provenance), reviewStatus="LegacyMappingNeedsReview"))
    selected_ids = {r['id'] for r in requirements}
    mappings = [m for m in mappings if m['source'] in selected_ids and m['target'] in selected_ids]
    frameworks.sort(key=lambda f:selected.index(f['id']))
    return dict(version=version, frameworks=frameworks, requirements=requirements, mappings=mappings,
                rulesHash=fingerprint([r["obligations"] for r in requirements]), status="Pilot — rule approval pending")


def installed():
    try:
        corpus = load()
        baseline_error = None
    except PolicyError as error:
        corpus = dict(status='Baseline unavailable', frameworks=[], requirements=[])
        baseline_error = str(error)
    supported = sum(all(a['rule'] for a in r['obligations']) for r in corpus['requirements'])
    available = [dict(**f, requirements=len(corpus['requirements']), automatedRequirements=supported) for f in corpus['frameworks']]
    availability_errors = {}
    try:
        existing = _library()
        for key in MANUAL_FRAMEWORKS:
            from . import updates
            refreshed = updates.current(key) if key in REVIEW_FRAMEWORKS else None
            if refreshed:
                available.append(dict(**refreshed['framework'], requirements=len(refreshed['requirements']), automatedRequirements=0))
                continue
            fw = existing.frameworks[key]
            rows = _controls(existing, key)
            if rows:
                available.append(dict(id=key, title=fw.name, edition=fw.revision, requirements=len(rows), automatedRequirements=0))
            else:
                availability_errors[key] = 'Local source not available.'
    except Exception:
        availability_errors['library'] = 'Local framework library could not be loaded.'
    if baseline_error:
        availability_errors['wa-csp'] = baseline_error
    from .packages import installation_root, verify
    packages = []
    for path in sorted(installation_root().glob('*.waccpack')):
        try:
            packages.append(verify(path))
        except PolicyError:
            packages.append(dict(version=path.stem, status='Invalid or no longer trusted'))
    return dict(corpusVersion=corpus.get('version', CORPUS_VERSION), installedPackages=packages, baselineError=baseline_error, status=corpus["status"], frameworks=corpus["frameworks"],
                requirements=len(corpus["requirements"]), ruleSupportedRequirements=supported,
                availableFrameworks=available, availabilityErrors=availability_errors,
                secondaryFrameworks=list(MANUAL_FRAMEWORKS))
