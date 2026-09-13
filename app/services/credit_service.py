import random
from datetime import datetime, date
from app.models.soft_pull_result import SoftPullResult

STATE_MAP = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming"
}


def verify_age(dob: str) -> bool:
    """Returns True if applicant is 18 or older."""
    birth_date = None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            birth_date = datetime.strptime(dob, fmt).date()
            break
        except ValueError:
            continue

    if birth_date is None:
        raise ValueError(f"Invalid date of birth format: {dob!r}. Expected YYYY-MM-DD or MM/DD/YYYY.")

    today = date.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    return age >= 18


def simulate_soft_pull(db, application_id) -> SoftPullResult:
    """
    Generates a SIMULATED credit score for an application and stores it.

    This is NOT a real credit bureau pull. It exists so the matching
    logic downstream (bank matching) has something real to query against
    while no live bureau/API integration is connected. Swap this out for
    a real soft-pull provider call when one is available — keep writing
    to the same SoftPullResult table so nothing downstream has to change.
    """
    simulated_score = random.randint(580, 800)

    result = SoftPullResult(
        application_id=application_id,
        credit_score=simulated_score,
        source="simulated",
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result
