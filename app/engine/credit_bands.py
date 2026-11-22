"""
Self-reported credit ranges. Used only when CREDIT_PROVIDER=self_reported.

Each band maps to its LOWER bound, so a self-reported range can only make
matching more conservative, never more generous.
"""

BANDS = {
    "below_580": 560,
    "580_649": 580,
    "650_679": 650,
    "680_719": 680,
    "720_plus": 720,
}

BAND_LABELS = {
    "below_580": "Below 580",
    "580_649": "580 - 649",
    "650_679": "650 - 679",
    "680_719": "680 - 719",
    "720_plus": "720 or higher",
}


def band_to_score(band):
    """Returns the conservative score for a band, or None if the band is unknown."""
    return BANDS.get((band or "").strip())
