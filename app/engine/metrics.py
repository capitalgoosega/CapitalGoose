"""Lending accuracy, as defined in the product doc: funded / fully submitted."""

MIN_SAMPLE = 50   # doc: report with the sample size until ~50 submitted applications
GOAL = 0.50


def accuracy_summary(submitted: int, funded: int, declined: int, withdrawn: int = 0):
    pending = max(submitted - funded - declined - withdrawn, 0)
    decided = funded + declined
    return {
        "fully_submitted": submitted,
        "funded": funded,
        "declined_by_lender": declined,
        "withdrawn": withdrawn,
        "pending": pending,
        # Headline number from the doc. Pending loans count in the denominator,
        # so this reads low early on while many files are still in review.
        "lending_accuracy": (funded / submitted) if submitted else None,
        # Companion number: of the files lenders have actually decided.
        "funded_of_decided": (funded / decided) if decided else None,
        "goal": GOAL,
        "sample_is_small": submitted < MIN_SAMPLE,
        "note": (
            f"Sample size is {submitted}; treat as directional until about {MIN_SAMPLE} submitted applications."
            if submitted < MIN_SAMPLE else None
        ),
    }
