"""Helpers for the no-login lender status links. Pure functions."""
import hashlib
import secrets

from app.engine import statuses as S

LINK_TTL_DAYS = 90

# What a lender can report with one tap, in order.
LENDER_ACTIONS = [
    (S.LENDER_RECEIVED, "We received the file"),
    (S.APPROVED, "Approved"),
    (S.CLOSING, "Closing"),
    (S.FUNDED, "Funded"),
    (S.DECLINED, "Declined"),
]
REASON_CODES = {
    "credit": "Credit",
    "cash_flow": "Cash flow / DSCR",
    "collateral": "Collateral",
    "time_in_business": "Time in business",
    "documentation": "Documentation incomplete",
    "policy": "Outside our credit box / policy",
    "applicant_withdrew": "Applicant stopped responding",
    "other": "Other",
}


def new_link_token():
    """Returns (token, sha256_hash). Only the hash is stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_link_token(token)


def hash_link_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def allowed_actions(current_status: str):
    return [(s, label) for s, label in LENDER_ACTIONS if S.can_transition(current_status, s)]
