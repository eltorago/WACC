"""Local, explainable topic matching between policy passages and requirements.

This is retrieval, not a compliance decision. Every requirement is searched
independently; framework mappings never transfer a match to another requirement.
"""
from collections import Counter, defaultdict
import math
import re
import unicodedata

from ..terms import ALIASES, STOPWORDS, normalise_token, tokenise
from .contracts import PolicyError

VERSION = 'policy-topics-1'
STATUSES = ('Mentioned', 'Related wording', 'Not mentioned', 'Unable to check')
DESCRIPTION = 'Matches compare wording and topics, with the original passages alongside each requirement.'
MAX_MATCHES = 5
MAX_WINDOWS = 50000
WORDS = re.compile(r"[\w]+(?:['’][\w]+)*", re.UNICODE)
GENERIC = {normalise_token(word) for word in STOPWORDS | {
    'security', 'cyber', 'cybersecurity', 'policy', 'policies', 'organisation',
    'entity', 'entities', 'control', 'controls', 'requirement', 'requirements',
    'appropriate', 'ensure', 'establish', 'established', 'maintain', 'maintained',
    'implement', 'implemented', 'document', 'documented', 'process', 'processes',
    'procedure', 'procedures', 'including', 'relevant', 'applicable', 'use', 'used',
    'using', 'based', 'information', 'management', 'manage', 'system', 'systems',
    'all', 'we', 'our', 'basis', 'perform', 'performed', 'undertake', 'undertaken',
}}
# Only unambiguous technical abbreviations; short words such as "ad" are excluded.
ACRONYMS = {key: value for key, value in ALIASES.items() if key in {'mfa', '2fa', 'siem', 'mdm', 'rto', 'rpo'}}
FREQUENCIES = {'annually':'annual', 'quarterly':'quarter', 'monthly':'month', 'weekly':'week', 'daily':'day'}
CAUTION = re.compile(r"\b(?:not|never|no longer|except|unless|may|might|should|consider|example|proposed|planned|disabled?|prohibited|without|cannot|lack|absent)\b", re.I)


def terms(text):
    """Return stems and their original offsets, retaining spelling/alias matches."""
    found = defaultdict(list)
    for match in WORDS.finditer(text):
        word = unicodedata.normalize('NFKC', match.group()).casefold()
        alternatives = [word, *ACRONYMS.get(word, [])]
        for alternative in alternatives:
            for token in tokenise(alternative):
                stem = normalise_token(FREQUENCIES.get(token, token))
                if len(stem) > 2 and not stem.isdigit() and stem not in GENERIC:
                    found[stem].append((match.start(), match.end()))
    return dict(found)


def windows(text):
    # Paragraphs/pages can be long. Match within a sentence, never by joining
    # unrelated passages. Bound sentence windows without losing any source text.
    for sentence in re.finditer(r'[^.!?;\n]+(?:[.!?;]|$)', text):
        start = sentence.start()
        while start < sentence.end():
            end = min(start + 1600, sentence.end())
            if end < sentence.end():
                boundary = text.rfind(' ', start + 800, end)
                if boundary > start:
                    end = boundary
            yield start, end
            start = end


def compare(requirements, documents, cancel=None):
    """Index passages once, then search all framework requirements against them."""
    active = [d for d in documents if d['included']]
    complete = bool(active) and all(d['status'] == 'Ready' and
        d.get('extractedPassageCount', len(d['passages'])) == len(d['passages']) for d in active)
    queries = [terms(r['authoritativeText'] + ' ' + r.get('context', '')) for r in requirements]
    frequencies, sizes = defaultdict(Counter), Counter()
    for requirement, query in zip(requirements, queries):
        key = requirement['frameworkId']
        frequencies[key].update(query.keys())
        sizes[key] += 1
    weights_by_framework = {key: {term: 1 + math.log((1 + sizes[key]) / (1 + count))
                                 for term, count in frequency.items()} for key, frequency in frequencies.items()}
    indexed, postings = [], defaultdict(set)
    for doc in active:
        for passage in doc['passages']:
            for start, end in windows(passage['text']):
                if cancel and cancel.is_set():
                    raise KeyboardInterrupt
                text = passage['text'][start:end]
                tokens = terms(text)
                index = len(indexed)
                if index >= MAX_WINDOWS:
                    raise PolicyError('The selected documents contain too many text sections. Split them into smaller comparisons.')
                indexed.append((doc, passage, start, end, tokens))
                for term in tokens:
                    postings[term].add(index)
    results = {}
    for requirement, query in zip(requirements, queries):
        if cancel and cancel.is_set():
            raise KeyboardInterrupt
        # A reference alone can be useful, but is always labelled related wording.
        references = [requirement['id'].casefold()]
        reference = requirement['officialReference']
        if reference and reference[0].isalpha():
            references.append(reference.casefold())
        candidates = set().union(*(postings.get(term, ()) for term in query)) if query else set()
        # Include windows with a named reference even when their wording differs.
        reference_terms = terms(' '.join(references))
        for term in reference_terms:
            candidates.update(postings.get(term, ()))
        matches = []
        core_terms = terms(requirement['authoritativeText'])
        weights = weights_by_framework[requirement['frameworkId']]
        total_weight = sum(weights[t] for t in query)
        for index in sorted(candidates):
            doc, passage, start, end, tokens = indexed[index]
            text = passage['text'][start:end]
            named = any(re.search(r'(?<!\w)' + re.escape(ref) + r'(?!\w)', text, re.I) for ref in references)
            shared = set(query) & set(tokens)
            proportion = sum(weights[t] for t in sorted(shared)) / total_weight if total_weight else 0
            enough = len(shared) >= 3 or len(query) == 2 and len(shared) == 2
            if not named and not (enough and proportion >= .35):
                continue
            cautions = []
            if CAUTION.search(text):
                cautions.append('Check the wording: this passage contains a qualification or negative statement.')
            heading = passage['locator'].get('heading', '')
            if re.search(r'\b(?:reference|glossary|example|background)\b', heading, re.I):
                cautions.append('This passage appears in reference or background material.')
            specific = bool(core_terms) and len(shared & set(core_terms)) >= min(2, len(core_terms))
            strong = enough and specific and proportion >= .65 and not cautions
            spans = sorted({(a, b) for term in shared for a, b in tokens[term]})
            matches.append(dict(documentId=doc['id'], documentHash=doc['sha256'], documentName=doc['name'],
                passageId=passage['id'], excerpt=text, locator=passage['locator'],
                start=start, end=end, matchedSpans=[dict(start=a, end=b) for a, b in spans],
                matchedTerms=sorted({text[a:b] for a, b in spans}),
                status='Mentioned' if strong else 'Related wording', cautions=cautions,
                reason='Named framework reference' if named and not enough else 'Shared requirement wording',
                score=round(proportion, 6)))
        # Keep the best window from each passage, then the five clearest passages.
        matches.sort(key=lambda m: (m['status'] != 'Mentioned', -m['score'], m['documentId'], m['passageId'], m['start']))
        unique = {}
        for match in matches:
            unique.setdefault((match['documentId'], match['passageId']), match)
        best = list(unique.values())
        status = ('Mentioned' if any(m['status'] == 'Mentioned' for m in best) else
                  'Related wording' if best else 'Not mentioned' if complete else 'Unable to check')
        results[requirement['id']] = dict(status=status, matches=best[:MAX_MATCHES], matchCount=len(best),
            searchComplete=complete, method=VERSION)
    return results


def for_run(run, cancel=None):
    if all('alignment' in row for row in run['requirements']):
        return {row['id']: row['alignment'] for row in run['requirements']}
    return compare(run['requirements'], run['documents'], cancel)


def summary(requirements, results):
    counts = Counter(results[r['id']]['status'] for r in requirements)
    return dict(requirements=len(requirements), counts={status: counts[status] for status in STATUSES})


def framework_summaries(run, results):
    grouped = defaultdict(list)
    for row in run['requirements']:
        grouped[row['frameworkId']].append(row)
    return [dict(id=f['id'], title=f['title'], edition=f['edition'], **summary(grouped[f['id']], results))
            for f in run['versions']['frameworks']]
