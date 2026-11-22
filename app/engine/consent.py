"""
Consent wording shown in the Capital Goose-hosted widget.

STATUS: APPROVED by Capital Goose's attorney (confirmed by Karon on 2026-11-22 as
exactly the text below, drafted originally by Claude). Not legal advice from Claude.
Live partners can create widget sessions once CONSENT_TEXT_APPROVED=true is set in Railway.

WHENEVER THE TEXT CHANGES, change CONSENT_VERSION too: every referral stores the
version string the applicant agreed to, which is the audit trail.

Paragraphs are separated by a blank line and rendered as separate paragraphs.
"""
import os

CONSENT_VERSION = "widget-2026-11-v2"

CONSENT_TEXT = (
    "By checking the box and typing my name below, I authorize Capital Goose and the lenders "
    "it works with to obtain my personal consumer credit report and related information from "
    "one or more consumer reporting agencies. I understand this is a soft inquiry that does not "
    "affect my credit score, and that it is requested only to evaluate whether I may qualify for "
    "the business financing I am asking about."
    "\n\n"
    "I understand that Capital Goose will share the information I provide here, and a summary of "
    "my credit information, with the lender it selects as the best fit, only so that lender can "
    "evaluate my request. Capital Goose may receive a referral fee from a lender if a loan is made; "
    "any such fee will be disclosed as required by law."
    "\n\n"
    "I agree that typing my name is my electronic signature and has the same effect as a "
    "handwritten signature, and that I may receive records about this request electronically."
    "\n\n"
    "I understand that finding out whether I may qualify is not a loan approval or a commitment to "
    "lend, and that final decisions are made by the lender after reviewing my documents. I confirm "
    "that the information I provided is accurate and that I am at least 18 years old."
)


def consent_text_approved() -> bool:
    return os.environ.get("CONSENT_TEXT_APPROVED", "").strip().lower() == "true"
