"""Group related source editions without counting a strategy twice."""
import re

ASD_FAMILY = 'asd-strategies'
ASD_LABEL = 'ACSC mitigation strategies (includes Essential Eight)'
E8_STRATEGIES = {
    'ac': 's01', 'pa': 's02', 'mac': 's03', 'uah': 's04',
    'rap': 's18', 'po': 's19', 'mfa': 's20', 'rb': 's34',
}
SUBSET_SOURCE = 'https://www.cyber.gov.au/business-government/asds-cyber-security-frameworks/essential-eight'


def family(key):
    return ASD_FAMILY if key == 'essential-eight' else key


def count(keys):
    return len({family(key) for key in keys})


def strategy_uid(uid):
    """The broader 2017 strategy corresponding to an E8 maturity row."""
    match = re.fullmatch(r'essential-eight:ml[123]-([a-z]+)-\d+', uid.lower())
    return 'asd-strategies:' + E8_STRATEGIES[match[1]] if match and match[1] in E8_STRATEGIES else None


def preferred_uids(uids):
    """Keep maturity detail in mixed results; retain all raw records for exact links.

    The two editions are not identical text. The broader strategy remains reachable
    from each maturity record, but is not another control in the same result set.
    """
    uids = set(uids)
    covered = {strategy_uid(uid) for uid in uids}
    return uids - covered
