"""
Consent wording shown in the Capital Goose-hosted widget.

THIS TEXT IS A PLACEHOLDER. It has not been reviewed by counsel. Live partners
cannot use the hosted widget until someone with authority sets
CONSENT_TEXT_APPROVED=true after the attorney signs off on the final wording
(and bumps CONSENT_VERSION whenever the text changes).
"""
import os

CONSENT_VERSION = "widget-2026-11-draft1"

CONSENT_TEXT = (
    "I authorize Capital Goose and its lending partners to obtain my personal credit report "
    "from a consumer reporting agency for the purpose of evaluating my business financing "
    "request. I understand this is a soft inquiry that does not affect my credit score, and "
    "that checking whether I may qualify is not a loan approval or a commitment to lend."
)


def consent_text_approved() -> bool:
    return os.environ.get("CONSENT_TEXT_APPROVED", "").strip().lower() == "true"
