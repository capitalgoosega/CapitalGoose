import requests
from app.core.config import settings

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

def run_credit_pull(ssn: str, first_name: str, last_name: str, dob: str, address: dict) -> int:

    url = "https://app.isoftpull.com/api/v2/reports"

    headers = {
        "api-key": settings.isoftpull_api_key,
        "api-secret": settings.isoftpull_api_secret,
        "Content-Type": "application/json"
    }

    payload = {
        "first_name": first_name,
        "last_name": last_name,
        "address": address["street"],
        "city": address["city"],
        "State": STATE_MAP.get(address["state"], address["state"]),
        "zip": address["zip"],
        "ssn": ssn.replace("-", ""),
        "date_of_birth": dob
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()

    credit_score_data = data.get("full_feed", {}).get("credit_score", {})
    for model in credit_score_data.values():
        score = model.get("score")
        if isinstance(score, int):
            return score

    raise ValueError("No valid credit score returned from iSoftPull")


def smart_quality_process(score: int):
    risk_level = "low"

    if score < 650:
        risk_level = "high"
    elif score < 700:
        risk_level = "medium"

    return {
        "score": score,
        "risk_level": risk_level,
        "passed": score >= 650
    }
