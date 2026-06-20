import requests
from app.core.config import settings


def run_credit_pull(ssn: str, first_name: str, last_name: str, dob: str, address: dict) -> int:
    """
    Calls the iSoftPull API to run a soft credit pull.
    Returns the credit score as an integer.
    """
    url = "https://api.isoftpull.com/v1/credit/pull"  # confirm exact endpoint in their docs

    headers = {
        "Authorization": f"Bearer {settings.isoftpull_api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "firstName": first_name,
        "lastName": last_name,
        "ssn": ssn,
        "dob": dob,          # e.g. "1990-01-15"
        "address": address   # e.g. {"street": "...", "city": "...", "state": "TX", "zip": "75001"}
    }

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    return data["creditScore"]  # adjust key to match their actual response shape


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
