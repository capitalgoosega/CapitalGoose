"""
Turns the per-lender eligibility checks into reasons a partner can show.

Partners see WHAT fit or what blocked the match, never a lender's actual
thresholds (those are the lender network and stay internal).
"""

PASS_TEXT = {
    "credit_score": "Credit profile fits this lender's range",
    "geography": "Lender serves the business's state",
    "years_in_business": "Time in business meets the lender's minimum",
    "annual_revenue": "Annual revenue meets the lender's minimum",
    "dscr": "Cash flow covers existing debt payments",
    "loan_amount": "Requested amount is within this lender's range",
    "pfs": "Personal Financial Statement will be required at handoff",
}

BLOCKER_TEXT = {
    "credit_score": "Credit profile is outside what our lenders accept",
    "geography": "No lender in our network serves this state yet",
    "years_in_business": "Time in business is under our lenders' minimums",
    "annual_revenue": "Annual revenue is under our lenders' minimums",
    "dscr": "Cash flow does not cover existing debt payments for our lenders",
    "loan_amount": "Requested amount is outside what our lenders fund",
    "pfs": "A Personal Financial Statement is required",
}


def match_reasons(checks):
    """checks: list of {'criterion','status','detail'} for the matched lender."""
    return [PASS_TEXT[c["criterion"]] for c in checks
            if c["status"] == "pass" and c["criterion"] in PASS_TEXT]


def no_match_blockers(all_lender_checks):
    """
    all_lender_checks: one checks-list per active lender. A criterion is a
    blocker when EVERY lender failed it (or it was unknown for every lender):
    those are the things that, if different, could have produced a match.
    Returns a list of {'criterion', 'message'}.
    """
    if not all_lender_checks:
        return [{"criterion": "no_lenders", "message": "No active lenders are configured"}]
    blockers = []
    seen = []
    for checks in all_lender_checks:
        for c in checks:
            if c["criterion"] not in seen:
                seen.append(c["criterion"])
    for criterion in seen:
        statuses = []
        for checks in all_lender_checks:
            for c in checks:
                if c["criterion"] == criterion:
                    statuses.append(c["status"])
        if statuses and all(s != "pass" for s in statuses):
            blockers.append({
                "criterion": criterion,
                "message": BLOCKER_TEXT.get(criterion, "Did not meet lender requirements"),
            })
    if not blockers:
        # Every single criterion was met by at least one lender, but no one
        # lender met all of them together.
        blockers.append({
            "criterion": "combination",
            "message": "No single lender met every requirement at once",
        })
    return blockers
