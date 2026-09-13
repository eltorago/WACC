"""Vocabulary regressions. Every case names the defect it came from.

These are the checks the search harness cannot make, because by the time a query has
been scored the evidence of which word failed to fold is gone. Each case here was a real
wrong answer first.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wacc.terms import (  # noqa: E402
    CONCEPTS_BY_KEY,
    alias_alternatives,
    concepts_for,
    content_stems,
    named_set,
    normalise_token,
    tokenise,
)


def same_stem(cases):
    out = []
    for left, right, why in cases:
        a, b = normalise_token(left), normalise_token(right)
        out.append((a == b, "%s / %s -> %s / %s" % (left, right, a, b), why))
    return out


CASES = same_stem([
    ("sanitised", "sanitization",
     "the ISM writes sanitised and NIST writes Media Sanitization. Folding the spelling "
     "was not enough: the -ise fold left sanitiz and the noun kept sanitization, so the "
     "query and the control never met and ISM-1742 was unreachable"),
    ("sanitise", "sanitised", "same family, one stem"),
    ("privilege", "privileges",
     "stripping -es from privileges gave privileg while privilege kept its e, so the "
     "privileged-access concept could not fire on the query that names it"),
    ("store", "stored", "the past tense of a verb ending in e adds d, not ed"),
    ("device", "devices", "same shape as privilege"),
    ("authenticate", "authentication",
     "ASD writes 'Use MFA to authenticate privileged users'; a query for multi-factor "
     "authentication scored nothing against it"),
    ("vulnerability", "vulnerabilities", "consonant plus y becomes ies"),
    ("log", "logging", "four-letter words are stemmed; logs has to reach log"),
    ("policy", "policies", "the ies rule must not fire twice"),
    ("access", "accesses",
     "accesses is the plural of access, and both must reach the same place"),
])

# Words that must NOT collapse, each because collapsing them broke something.
APART = [
    ("account", "accountable",
     "stripping four letters let a query for accounts match Accountable Authority"),
    ("size", "sanitize",
     "size ends in -ize and is not that family; the root guard is what stops it"),
    ("advise", "advertize",
     "advise is spelled with an s on both sides of the Pacific"),
    ("trustees", "trust",
     "a trustee is a person and trust is the architecture. Stripping -es after any "
     "letter reduced trustees to trust, so a zero trust query answered with governing "
     "body membership"),
    ("employees", "employ",
     "same rule, same shape: the plural of a person-noun must not become the verb"),
    ("licensees", "license",
     "a licensee is a party to a licence, not the licence"),
]


def run() -> int:
    failures = 0
    for ok, detail, why in CASES:
        if ok:
            print("  pass  same stem   %s" % detail)
        else:
            failures += 1
            print("  FAIL  same stem   %s\n        from: %s" % (detail, why))

    for left, right, why in APART:
        a, b = normalise_token(left), normalise_token(right)
        if a != b:
            print("  pass  kept apart  %s / %s -> %s / %s" % (left, right, a, b))
        else:
            failures += 1
            print("  FAIL  kept apart  %s and %s both became %s\n        from: %s"
                  % (left, right, a, why))

    # 'access' is not a plural: the bare s rule must leave it whole.
    if normalise_token("access") == "access":
        print("  pass  plural      access survives the s rule")
    else:
        failures += 1
        print("  FAIL  plural      access became %s" % normalise_token("access"))

    # Hyphen and space are the same separator, because SQLite's tokeniser says so and
    # the two spellings were returning different results for one question.
    if content_stems("multi-factor authentication") == content_stems(
        "multi factor authentication"
    ):
        print("  pass  separators  hyphen and space give the same stems")
    else:
        failures += 1
        print("  FAIL  separators  'multi-factor' and 'multi factor' still differ")

    # An alias is an alternative spelling of one term, not three extra terms.
    forms = dict(alias_alternatives(tokenise("MFA")))["mfa"]
    if forms == [["mfa"], ["multi", "factor", normalise_token("authentication")]]:
        print("  pass  alias       MFA carries its expansion as one alternative")
    else:
        failures += 1
        print("  FAIL  alias       MFA expanded to %s" % forms)

    # A short alias only fires when the query is plainly the abbreviation.
    long_query = tokenise("the ad server is patched every month")
    if dict(alias_alternatives(long_query))["ad"] == [["ad"]]:
        print("  pass  alias       'ad' in a sentence is not Active Directory")
    else:
        failures += 1
        print("  FAIL  alias       'ad' expanded inside a long query")

    # The Essential Eight is a group. Naming one strategy must reach a policy that
    # mandates the group, and must not reach the other seven strategies.
    e8 = CONCEPTS_BY_KEY["essential-eight"]
    if "multi-factor authentication" in e8.phrases and e8.control_phrases == [
        "essential eight", "essential 8"
    ]:
        print("  pass  group       Essential Eight expands queries, not controls")
    else:
        failures += 1
        print("  FAIL  group       Essential Eight member phrases leak into controls: %s"
              % e8.control_phrases)

    # A carriage service provider is who a SOCI entity is, not its supply chain.
    supply = CONCEPTS_BY_KEY["supply-chain"]
    if "carriage service provider" in supply.excluding:
        print("  pass  exclusion   carriage service provider excluded from supply chain")
    else:
        failures += 1
        print("  FAIL  exclusion   supply-chain no longer excludes carriage service")

    # Naming a document is not searching for a word in it.
    if named_set("ISM") and named_set("ISM")[0] == "ism" and named_set("E8") and (
        named_set("E8")[1] == "essential_eight_maturity"
    ):
        print("  pass  named set   ISM and E8 resolve to a document, not a term")
    else:
        failures += 1
        print("  FAIL  named set   ISM or E8 no longer resolves to a document")

    if named_set("media sanitisation") is not None:
        failures += 1
        print("  FAIL  named set   a topical query was treated as a document name")
    else:
        print("  pass  named set   a topical query is not treated as a document name")

    # Question words carry no subject. 'how' matched the OAG heading 'Understand how
    # accounts are used' and put account visibility in an incident-timeframe result.
    if "how" not in content_stems("how quickly must an incident be reported"):
        print("  pass  stopwords   question words are not search terms")
    else:
        failures += 1
        print("  FAIL  stopwords   'how' is being searched for")

    # A negation is never the optional half of a pattern.
    if "not" not in content_stems("access is not permitted"):
        print("  pass  negation    obligation words stay out of retrieval terms")
    else:
        failures += 1
        print("  FAIL  negation    'not' entered the retrieval terms")

    print("\nterms: %d failed" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
