"""Presentation groups preserve source authority while combining governance results."""
from ..analysis import TierBand
from ..model import Tier


def result_groups(analysis):
    merged = TierBand(Tier.OUTCOME)
    remainder = []
    for band in analysis.bands:
        if band.tier in (Tier.STATUTE, Tier.MANDATED_POLICY, Tier.OUTCOME):
            merged.coverage.extend(band.coverage)
        else:
            remainder.append(band)
    merged.coverage.sort(key=lambda c: c.framework.short_name.casefold())
    return [merged] + remainder


def group_label(band):
    return {
        Tier.OUTCOME: 'Outcomes / maturity',
        Tier.CATALOGUE: 'Control catalogue',
        Tier.SPECIFICATION: 'Technical specifications',
    }[band.tier]
