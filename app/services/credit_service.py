from datetime import datetime, date


def verify_age(dob: str) -> bool:
    """Returns True if applicant is 18 or older."""
    try:
        birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        birth_date = datetime.strptime(dob, "%m/%d/%Y").date()

    today = date.today()
    age = today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )
    return age >= 18