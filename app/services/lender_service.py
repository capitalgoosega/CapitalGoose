from app.models.bank_profile import BankProfile


def choose_lender(db, credit_score: int, applicant_state: str = None):
    """
    Queries BankProfile for an active bank whose credit score range
    includes the applicant's score AND whose geographic scope covers
    the applicant's business state.

    Returns the matched BankProfile, or None if no bank matches.

    NOTE: matching is currently credit score + geography only.
    Cash flow (DSCR), PFS, and years-in-business requirements from the
    mapping table are stored on BankProfile for reference but are NOT
    enforced here, since Cognito Forms doesn't yet collect the
    structured data needed to check them automatically.

    Selection when multiple banks qualify: picks the one with the
    highest min_credit_score the applicant still clears (best-fit
    tier). Ties broken alphabetically by name for determinism.
    """
    candidates = (
        db.query(BankProfile)
        .filter(BankProfile.active == True)  # noqa: E712
        .filter(BankProfile.min_credit_score <= credit_score)
        .filter(BankProfile.max_credit_score >= credit_score)
        .all()
    )

    matches = [b for b in candidates if b.accepts_state(applicant_state)]

    if not matches:
        return None

    return sorted(matches, key=lambda b: (-b.min_credit_score, b.name))[0]
