def choose_lender(loan_type, score):
    """
    Simulates bank system routing.
    """

    if score >= 750:
        return "Prime National Bank"

    if loan_type.lower() == "sba":
        return "SBA Bank"

    if loan_type.lower() == "equipment":
        return "Equipment Finance Group"

    return "Advance Lender"
