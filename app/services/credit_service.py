import random


def run_credit_pull():
    """
    Simulates ISOFTPULL credit API.
    """
    return random.randint(580, 800)


def smart_quality_process(score: int):
    """
    Simulates smart underwriting quality process.
    """

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
