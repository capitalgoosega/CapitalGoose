import json

from app.models.application_financials import ApplicationFinancials
from app.models.bank_profile import BankProfile, to_state_code
from app.models.eligibility_result import LenderEligibilityResult


def parse_number(value):
    """Turns '$1,250.50', '(500)', 1250 or '1250' into a float. Returns None if it can't."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("$", "").replace(",", "").replace(" ", "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _pick(data, *keys):
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return parse_number(data[key])
    return None


def extract_financials(data):
    data = data if isinstance(data, dict) else {}
    years = _pick(data, "YearsInBusiness", "Entry.YearsInBusiness")
    revenue = _pick(data, "AnnualRevenue", "Entry.AnnualRevenue")
    noi = _pick(data, "AnnualNetOperatingIncome", "Entry.AnnualNetOperatingIncome")
    debt = _pick(data, "AnnualDebtPayments", "Entry.AnnualDebtPayments")

    # DSCR = annual net operating income / annual debt payments.
    # Existing debt only for now: the new loan's payment is not included.
    dscr = None
    if noi is not None and debt is not None and debt > 0:
        dscr = noi / debt

    return {
        "years_in_business": years,
        "annual_revenue": revenue,
        "annual_net_operating_income": noi,
        "annual_debt_payments": debt,
        "dscr": dscr,
    }


def has_pfs(document_urls):
    for key in document_urls:
        normalized = str(key).lower().replace(" ", "").replace("_", "")
        if "personalfinancialstatement" in normalized:
            return True
    return False


def _check(criterion, status, detail):
    return {"criterion": criterion, "status": status, "detail": detail}


def _evaluate_lender(lender, credit_score, state, fin, pfs_uploaded):
    checks = []

    # Credit score
    if credit_score is None:
        checks.append(_check("credit_score", "unknown", "no credit score available"))
    elif lender.min_credit_score <= credit_score <= lender.max_credit_score:
        checks.append(_check("credit_score", "pass", f"{credit_score} is within {lender.min_credit_score}-{lender.max_credit_score}"))
    else:
        checks.append(_check("credit_score", "fail", f"{credit_score} is outside {lender.min_credit_score}-{lender.max_credit_score}"))

    # Geography
    allowed = (lender.allowed_states or "").strip().upper()
    if not allowed:
        checks.append(_check("geography", "fail", "lender footprint not confirmed"))
    elif allowed == "ALL":
        checks.append(_check("geography", "pass", "lender covers all states"))
    else:
        code = to_state_code(state)
        if not code:
            checks.append(_check("geography", "unknown", "applicant state missing or not recognized"))
        elif code in {s.strip() for s in allowed.split(",")}:
            checks.append(_check("geography", "pass", f"{code} is in the lender's footprint"))
        else:
            checks.append(_check("geography", "fail", f"{code} is not in the lender's footprint"))

    # Years in business
    if lender.years_in_business_required is not None:
        years = fin["years_in_business"]
        if years is None:
            checks.append(_check("years_in_business", "unknown", "years in business not provided or not a number"))
        elif years >= lender.years_in_business_required:
            checks.append(_check("years_in_business", "pass", f"{years:g} years meets the {lender.years_in_business_required}-year minimum"))
        else:
            checks.append(_check("years_in_business", "fail", f"{years:g} years is under the {lender.years_in_business_required}-year minimum"))

    # Annual revenue
    if lender.min_annual_revenue is not None:
        revenue = fin["annual_revenue"]
        if revenue is None:
            checks.append(_check("annual_revenue", "unknown", "annual revenue not provided or not a number"))
        elif revenue >= lender.min_annual_revenue:
            checks.append(_check("annual_revenue", "pass", f"revenue meets the ${lender.min_annual_revenue:,} minimum"))
        else:
            checks.append(_check("annual_revenue", "fail", f"revenue is under the ${lender.min_annual_revenue:,} minimum"))

    # DSCR
    if lender.min_dscr is not None:
        noi = fin["annual_net_operating_income"]
        debt = fin["annual_debt_payments"]
        if noi is None or debt is None:
            checks.append(_check("dscr", "unknown", "net operating income or debt payments not provided"))
        elif debt < 0:
            checks.append(_check("dscr", "unknown", "debt payments can't be negative"))
        elif debt == 0:
            if noi > 0:
                checks.append(_check("dscr", "pass", "no existing debt payments and positive operating income"))
            else:
                checks.append(_check("dscr", "fail", "no operating income"))
        else:
            dscr = noi / debt
            if dscr >= lender.min_dscr:
                checks.append(_check("dscr", "pass", f"DSCR {dscr:.2f} meets the {lender.min_dscr:.2f} minimum"))
            else:
                checks.append(_check("dscr", "fail", f"DSCR {dscr:.2f} is under the {lender.min_dscr:.2f} minimum"))

    # Personal Financial Statement
    if lender.pfs_required:
        if pfs_uploaded:
            checks.append(_check("pfs", "pass", "Personal Financial Statement uploaded"))
        else:
            checks.append(_check("pfs", "fail", "no Personal Financial Statement uploaded"))

    return checks


def save_financials(db, application_id, fin):
    db.query(ApplicationFinancials).filter(ApplicationFinancials.application_id == application_id).delete()
    db.add(ApplicationFinancials(application_id=application_id, **fin))
    db.commit()


def evaluate_lenders(db, application_id, credit_score, state, fin, pfs_uploaded):
    """
    Checks the applicant against every active lender, saves the result
    and reasons for each, and returns the eligible lenders, best fit first
    (highest minimum credit score, then name).
    """
    lenders = (
        db.query(BankProfile)
        .filter(BankProfile.active == True)  # noqa: E712
        .order_by(BankProfile.id)
        .all()
    )

    db.query(LenderEligibilityResult).filter(LenderEligibilityResult.application_id == application_id).delete()

    eligible = []
    for lender in lenders:
        checks = _evaluate_lender(lender, credit_score, state, fin, pfs_uploaded)
        is_eligible = all(c["status"] == "pass" for c in checks)
        db.add(LenderEligibilityResult(
            application_id=application_id,
            lender_id=lender.id,
            lender_name=lender.name,
            eligible=is_eligible,
            details=json.dumps(checks),
        ))
        if is_eligible:
            eligible.append(lender)

    db.commit()

    eligible.sort(key=lambda b: (-b.min_credit_score, b.name))
    return eligible
