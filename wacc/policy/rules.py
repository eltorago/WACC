"""Finite, data-only rule language. Corpus text never becomes code or regex."""
import re
from .contracts import PolicyError
from .documents import normalise

OPERATORS = {"all", "any", "phrases", "pattern"}
PATTERNS = {
    "mandatory": r"\b(?:must|shall|are required to|is required to)\b",
    "universal_staff": r"\b(?:all (?:staff|personnel|employees)|every (?:employee|staff member)|each (?:employee|staff member))\b",
    "training_action": r"\b(?:complete|undertake|attend|receive)\b",
    "training_commitment": r"\b(?:all (?:staff|personnel|employees)|every employee|each employee) (?:must|shall|are required to) (?:complete|undertake|attend|receive) (?:annual |the )?(?:cyber ?security|security) awareness training\b",
    "training_annual": r"\b(?:(?:annual (?:cyber ?security|security) awareness training)|(?:(?:cyber ?security|security) awareness training (?:annually|every year|each year|on an annual basis|at least once (?:a|per) year|every 12 months)))\b",
    "annual": r"\b(?:annually|every year|each year|on an annual basis|at least once (?:a|per) year|every 12 months)\b",
    "restrict_issuance": r"\b(?:must|shall) (?:only be issued|be issued only)\b",
}
AMBIGUITY = re.compile(r"\b(?:should|may|might|consider|where practical|unless|except|example|glossary|definition|according to|quoted|quotation)\b", re.I)
NEGATIVE = re.compile(r"\b(?:not required|not mandatory|need not|must not|shall not|do not|does not|are not required|is not required|no longer required)\b", re.I)


def validate_rule(node, depth=0):
    if not isinstance(node, dict) or len(node) != 1 or depth > 8:
        raise PolicyError("Invalid rule shape or nesting depth.", 5)
    operator, value = next(iter(node.items()))
    if operator not in OPERATORS:
        raise PolicyError("Unsupported rule operator: " + str(operator), 5)
    if operator in ("all", "any"):
        if not isinstance(value, list) or not 1 <= len(value) <= 16:
            raise PolicyError("Rule group must contain 1–16 conditions.", 5)
        for child in value:
            validate_rule(child, depth + 1)
    elif operator == "phrases":
        if not isinstance(value, list) or not 1 <= len(value) <= 32 or any(not isinstance(v, str) or not 1 <= len(v) <= 150 for v in value):
            raise PolicyError("Invalid phrase list.", 5)
    elif value not in PATTERNS:
        raise PolicyError("Unsupported rule pattern.", 5)


def check(node, sentence, offset, mapping):
    operator, value = next(iter(node.items()))
    if operator in ("all", "any"):
        children = [check(c, sentence, offset, mapping) for c in value]
        ok = all(c[0] for c in children) if operator == "all" else any(c[0] for c in children)
        return ok, [s for c in children for s in c[1]], [t for c in children for t in c[2]]
    if operator == "pattern":
        patterns = [(value, PATTERNS[value])]
    else:
        patterns = [(term, r"(?<!\w)" + re.escape(normalise(term)[0]) + r"(?!\w)") for term in value]
    spans = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, sentence):
            begin, end = offset + match.start(), offset + match.end()
            spans.append(dict(start=mapping[begin][0], end=mapping[end-1][1],
                              normalisedStart=begin, normalisedEnd=end, signal=label))
    return bool(spans), spans, [dict(operator=operator, condition=value, passed=bool(spans))]


def evaluate(rule, passage):
    validate_rule(rule)
    normal, mapping = normalise(passage["text"])
    results = []
    for match in re.finditer(r"[^.!?;]+(?:[.!?;]|$)", normal):
        sentence = match.group()
        ok, spans, trace = check(rule, sentence, match.start(), mapping)
        # A relevant phrase is a retrieval candidate, not evidence of completeness.
        relevant = any(s["signal"] not in PATTERNS for s in spans)
        if not relevant:
            continue
        negative = bool(NEGATIVE.search(sentence))
        ambiguous = bool(AMBIGUITY.search(sentence)) or sentence.strip().startswith(('"', '“', '>')) or bool(re.search(r'\b(?:background|glossary|definitions|examples|quoted material)\b', passage['locator'].get('heading',''), re.I))
        state = "Contradiction" if negative else "Ambiguous" if ambiguous else "Matched" if ok else "Missing"
        results.append(dict(state=state, matchedSpans=spans, checks=trace,
                            context="same_sentence", ruleSatisfied=ok and not negative and not ambiguous))
    return results
