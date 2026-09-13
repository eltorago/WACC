"""OSCAL catalog and profile loader.

Serves the ISM and SP 800-53, which are the two corpora that arrive as the
publisher's own machine-readable release.

What this extracts rather than infers:
  - control text, from statement parts, with parameter placeholders resolved
  - the publisher's own labels, all of them, so AC-06(05) and AC-6(5) both resolve
  - ISM applicability, which is a list of classification levels
  - 800-53A assessment objectives and methods, which ship inside the 800-53 catalog
  - baseline membership, from profiles, as a publisher tag
"""

import json
import re
from typing import Dict, Iterable, List, Optional, Tuple

from ..model import (
    Control,
    Corpus,
    Framework,
    Origin,
    Provenance,
    Statement,
    StatementKind,
)

_PARAM_RE = re.compile(r"\{\{\s*insert:\s*param,\s*([^}\s]+)\s*\}\}")
_MAX_PARAM_PASSES = 5


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def load_catalog(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["catalog"]


def load_profile(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)["profile"]


def catalog_version(catalog: dict) -> Tuple[Optional[str], Optional[str]]:
    """Revision and where the claim comes from. Never guessed."""
    meta = catalog.get("metadata", {})
    version = meta.get("version")
    return (version, "OSCAL metadata version field") if version else (None, None)


# --------------------------------------------------------------------------
# Parameters
# --------------------------------------------------------------------------


def _param_labels(control: dict) -> Dict[str, str]:
    """A readable stand-in for each parameter this control declares."""
    out: Dict[str, str] = {}
    for p in control.get("params", []) or []:
        pid = p.get("id")
        if not pid:
            continue
        if p.get("label"):
            out[pid] = "[%s]" % p["label"]
        elif p.get("select"):
            # An OSCAL choice is a plain string in most catalogs and an object with
            # a value in others. Guard the type rather than assuming either.
            choices = []
            for ch in p["select"].get("choice", []) or []:
                if isinstance(ch, str):
                    choices.append(ch)
                elif isinstance(ch, dict):
                    value = ch.get("value") or ch.get("prose") or ""
                    if value:
                        choices.append(str(value))
            out[pid] = "[%s]" % " or ".join(choices) if choices else "[selection]"
        elif p.get("values"):
            vals = p["values"]
            out[pid] = ", ".join(vals) if isinstance(vals, list) else str(vals)
        else:
            out[pid] = "[%s]" % pid
    return out


def resolve_params(text: str, labels: Dict[str, str]) -> str:
    """Substitute placeholders, repeatedly.

    A parameter label can itself contain a placeholder, so one pass leaves
    {{ insert: param, ... }} in shipped text. Passes stop when nothing changes.
    """
    for _ in range(_MAX_PARAM_PASSES):
        replaced = _PARAM_RE.sub(lambda m: labels.get(m.group(1), "[%s]" % m.group(1)), text)
        if replaced == text:
            return replaced
        text = replaced
    return text


# --------------------------------------------------------------------------
# Parts
# --------------------------------------------------------------------------


def _part_text(part: dict, labels: Dict[str, str], depth: int = 0) -> str:
    """Flatten a part and its children into readable prose.

    800-53 statements nest lettered items; the label prop carries 'a.', 'b.' and so
    on, and dropping it loses which obligation is which.
    """
    pieces: List[str] = []
    label = ""
    for prop in part.get("props", []) or []:
        if prop.get("name") == "label":
            label = str(prop.get("value") or "").strip()
            break
    prose = (part.get("prose") or "").strip()
    if prose:
        prefix = ("  " * depth) + (label + " " if label else "")
        pieces.append(prefix + prose)
    for child in part.get("parts", []) or []:
        child_text = _part_text(child, labels, depth + 1)
        if child_text:
            pieces.append(child_text)
    return "\n".join(pieces)


def _parts_named(control: dict, name: str) -> List[dict]:
    return [p for p in control.get("parts", []) or [] if p.get("name") == name]


def statement_text(control: dict, labels: Dict[str, str]) -> str:
    chunks = [_part_text(p, labels) for p in _parts_named(control, "statement")]
    text = "\n".join(c for c in chunks if c).strip()
    return resolve_params(text, labels)


def guidance_text(control: dict, labels: Dict[str, str]) -> str:
    chunks = [_part_text(p, labels) for p in _parts_named(control, "guidance")]
    return resolve_params("\n".join(c for c in chunks if c).strip(), labels)


# --------------------------------------------------------------------------
# Props
# --------------------------------------------------------------------------


def prop_values(node: dict, name: str) -> List[str]:
    out = []
    for p in node.get("props", []) or []:
        if p.get("name") == name:
            v = p.get("value")
            if v is not None and str(v) not in out:
                out.append(str(v))
    return out


def preferred_label(control: dict) -> Optional[str]:
    """The label a person would type.

    NIST prints AC-06(05) and AC-6(5) as separate label props on the same control.
    Both fold to one key, so the shortest is kept for display and the rest are kept
    as alternates for lookup.

    ISM security controls carry no label at all, so the OSCAL id becomes the
    identifier with its prefix cased the way the publisher writes it: ISM-1997.
    """
    labels = prop_values(control, "label")
    if labels:
        return sorted(labels, key=lambda s: (len(s), s))[0]
    oscal_id = control.get("id")
    if not oscal_id:
        return None
    m = re.match(r"^([a-z]+)([-_].*)$", str(oscal_id))
    return m.group(1).upper() + m.group(2) if m else str(oscal_id)


def real_title(control: dict, identifier: str) -> Optional[str]:
    """A title that only restates the identifier is not a title.

    Every one of the ISM's 1,143 security controls is titled 'Control: ism-NNNN'.
    Treating that as a label would be harmless; the damage comes from the repair
    someone reaches for next, which is to borrow the section heading instead. Those
    headings are shared by siblings, so a harness generating queries from titles
    would be asking the same question many times over and calling it coverage.
    """
    title = (control.get("title") or "").strip()
    if not title:
        return None
    oscal_id = str(control.get("id") or "")
    stripped = title.lower().replace("control:", "").strip()
    if stripped in (oscal_id.lower(), identifier.lower()):
        return None
    return title


# --------------------------------------------------------------------------
# Walking
# --------------------------------------------------------------------------


def walk_controls(
    node: dict, group_path: Tuple[str, ...] = (), depth: int = 0
) -> Iterable[Tuple[dict, Tuple[str, ...], int, Optional[str]]]:
    """Yield (control, group titles above it, nesting depth, parent control id)."""
    for group in node.get("groups", []) or []:
        title = group.get("title") or ""
        for item in walk_controls(group, group_path + (title,), depth):
            yield item
    for control in node.get("controls", []) or []:
        yield control, group_path, depth, node.get("id") if "id" in node else None
        for item in _walk_children(control, group_path, depth + 1):
            yield item


def _walk_children(control: dict, group_path: Tuple[str, ...], depth: int):
    for child in control.get("controls", []) or []:
        yield child, group_path, depth, control.get("id")
        for item in _walk_children(child, group_path, depth + 1):
            yield item


# --------------------------------------------------------------------------
# Loading into the corpus
# --------------------------------------------------------------------------


def load_into(
    corpus: Corpus,
    framework: Framework,
    catalog_path: str,
    applicability_prop: Optional[str] = None,
    assessment_publisher: Optional[str] = None,
) -> Dict[str, int]:
    """Load one OSCAL catalog. Returns counts for the load report."""
    catalog = load_catalog(catalog_path)
    revision, basis = catalog_version(catalog)
    if revision:
        framework.revision = revision
        framework.revision_source = basis

    counts = {"controls": 0, "assessment_objectives": 0, "assessment_methods": 0}
    seen_ids: Dict[str, str] = {}

    for control, group_path, depth, parent_id in walk_controls(catalog):
        labels = _param_labels(control)
        identifier = preferred_label(control) or control.get("id") or ""
        text = statement_text(control, labels)
        guidance = guidance_text(control, labels)

        attributes: Dict[str, object] = {
            "oscal_id": control.get("id"),
            "group_path": list(group_path),
        }
        if control.get("class"):
            attributes["class"] = control["class"]
        if guidance:
            attributes["guidance"] = guidance
        alt = [l for l in prop_values(control, "label") if l != identifier]
        if alt:
            attributes["alternate_labels"] = alt

        publisher_tags: Dict[str, object] = {}
        if applicability_prop:
            values = prop_values(control, applicability_prop)
            applicability: object = values if values else None
        else:
            applicability = None
        for extra in ("implementation-level", "status", "revision", "updated"):
            vals = prop_values(control, extra)
            if vals:
                publisher_tags[extra] = vals if len(vals) > 1 else vals[0]

        c = Control(
            framework_key=framework.key,
            identifier=identifier,
            title=real_title(control, identifier),
            text=text,
            depth=min(depth, max(0, len(framework.levels) - 1)),
            parent_uid=None,
            applicability=applicability,
            publisher_tags=publisher_tags,
            attributes=attributes,
            section_ref=" > ".join(t for t in group_path if t) or None,
            origin=Origin.GENERATED,
        )
        oscal_id = control.get("id") or ""
        if oscal_id:
            seen_ids[oscal_id] = c.uid
        corpus.add_control(c)
        counts["controls"] += 1

        if assessment_publisher:
            counts_add = _load_assessment(
                corpus, c, control, labels, assessment_publisher
            )
            counts["assessment_objectives"] += counts_add[0]
            counts["assessment_methods"] += counts_add[1]

    _link_parents(corpus, catalog, framework, seen_ids)
    return counts


def _load_assessment(
    corpus: Corpus,
    control: Control,
    raw: dict,
    labels: Dict[str, str],
    publisher: str,
) -> Tuple[int, int]:
    """Attach the publisher's own assessment procedures.

    These are NIST's, not this tool's. Provenance published, publisher named, so a
    derived procedure can never be mistaken for one NIST wrote.
    """
    objectives = methods = 0
    for part in _parts_named(raw, "assessment-objective"):
        text = resolve_params(_part_text(part, labels), labels)
        if not text:
            continue
        corpus.add_statement(
            Statement(
                control_uid=control.uid,
                kind=StatementKind.TEST_PROCEDURE,
                text=text,
                provenance=Provenance.PUBLISHED,
                published_by=publisher,
                published_ref=part.get("id"),
            )
        )
        objectives += 1
    for part in _parts_named(raw, "assessment-method"):
        method = (prop_values(part, "method") or [""])[0]
        objects = [
            resolve_params(_part_text(p, labels), labels)
            for p in part.get("parts", []) or []
            if p.get("name") == "assessment-objects"
        ]
        body = "\n".join(o for o in objects if o).strip()
        if not body:
            continue
        prefix = "%s: " % method.title() if method else ""
        corpus.add_statement(
            Statement(
                control_uid=control.uid,
                kind=StatementKind.TEST_PROCEDURE,
                text=prefix + body,
                provenance=Provenance.PUBLISHED,
                published_by=publisher,
                published_ref=part.get("id"),
            )
        )
        methods += 1
    return objectives, methods


def _link_parents(
    corpus: Corpus, catalog: dict, framework: Framework, seen: Dict[str, str]
) -> None:
    """Second pass, because a child can be read before its parent is in the corpus."""
    for control, _group_path, _depth, parent_id in walk_controls(catalog):
        if not parent_id:
            continue
        child_uid = seen.get(control.get("id") or "")
        parent_uid = seen.get(parent_id)
        if child_uid and parent_uid and child_uid in corpus.controls:
            corpus.controls[child_uid].parent_uid = parent_uid


# --------------------------------------------------------------------------
# Profiles as publisher tags
# --------------------------------------------------------------------------


def profile_control_ids(profile_path: str) -> List[str]:
    profile = load_profile(profile_path)
    out: List[str] = []
    for imp in profile.get("imports", []) or []:
        for inc in imp.get("include-controls", []) or []:
            for cid in inc.get("with-ids", []) or []:
                out.append(cid)
    return out


def apply_profile_tag(
    corpus: Corpus, framework: Framework, profile_path: str, tag_name: str, tag_value: str
) -> int:
    """Mark every control a published profile selects.

    Baseline membership is the publisher's answer to 'is this in the baseline I am
    held to'. Essential Eight maturity and 800-53B low/moderate/high are the same
    kind of fact, and both arrive this way.
    """
    ids = set(profile_control_ids(profile_path))
    hits = 0
    for control in corpus.controls_for(framework.key):
        if control.attributes.get("oscal_id") in ids:
            existing = control.publisher_tags.get(tag_name)
            values = list(existing) if isinstance(existing, list) else (
                [existing] if existing else []
            )
            if tag_value not in values:
                values.append(tag_value)
            control.publisher_tags[tag_name] = values
            control.obligation_provenance = Provenance.PUBLISHED
            hits += 1
    if hits == 0:
        corpus.load_warnings.append(
            "profile %s selected %d ids but tagged no controls in %s; the id form "
            "probably does not match" % (profile_path, len(ids), framework.key)
        )
    return hits
