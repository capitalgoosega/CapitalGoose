from app.models.bank_profile import BankProfile


def choose_lender(db, loan_type: str, credit_score: int):
    """
    Queries BankProfile for an active bank that accepts this loan_type
    and whose credit score range includes the applicant's score.

    Returns the matched BankProfile, or None if no bank matches.

    Selection when multiple banks qualify: picks the one with the
    highest min_credit_score that the applicant still clears — i.e.
    the best-fit tier, not just the first match. Replace this
    tie-breaking rule if you want different matching priorities
    (e.g. by loan amount capacity) once real bank data is in place.
    """
    candidates = (
        db.query(BankProfile)
        .filter(BankProfile.active == True)  # noqa: E712
        .filter(BankProfile.min_credit_score <= credit_score)
        .filter(BankProfile.max_credit_score >= credit_score)
        .all()
    )

    matches = [b for b in candidates if b.accepts_loan_type(loan_type)]

    if not matches:
        return None

    return max(matches, key=lambda b: b.min_credit_score)
