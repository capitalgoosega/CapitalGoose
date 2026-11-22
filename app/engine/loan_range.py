"""Loan-size rules for lenders. Pure functions."""


def check_loan_amount(min_amount, max_amount, amount):
    """Returns (status, detail) in the same shape as the other eligibility checks,
    or None when the lender has no loan-size limits configured."""
    if min_amount is None and max_amount is None:
        return None
    if amount is None:
        return "unknown", "loan amount not provided"
    if min_amount is not None and amount < min_amount:
        return "fail", f"${amount:,} is under the ${min_amount:,} minimum"
    if max_amount is not None and amount > max_amount:
        return "fail", f"${amount:,} is over the ${max_amount:,} maximum"
    return "pass", "loan amount is within the lender's range"


def likely_range(min_amount, max_amount):
    """What a partner may be shown. None when the lender hasn't set limits."""
    if min_amount is None and max_amount is None:
        return None
    return {"min": min_amount, "max": max_amount}
