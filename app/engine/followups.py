"""
When to nudge. Pure functions, no database.

Lender: a weekly status reminder while a file is still open (up to 8 weeks).
Borrower: a check-in at 30, 60 and 90 days after submission.

Only the CURRENT window is ever sent. If the app was down for a month, we do
not send a burst of old reminders when it comes back.
"""
from datetime import timedelta

from app.engine import statuses as S

ACTIVE = {S.SUBMITTED, S.LENDER_RECEIVED, S.APPROVED, S.CLOSING}
MAX_LENDER_WEEKS = 8
BORROWER_DAYS = (30, 60, 90)
BORROWER_GRACE_DAYS = 14
BORROWER_ANSWERS = {
    "funded": "Yes, I received the funds",
    "waiting": "Still waiting to hear back",
    "other_option": "I went with another option",
    "not_needed": "I no longer need the loan",
}


def lender_kind(week: int) -> str:
    return f"lender_w{week}"


def borrower_kind(days: int) -> str:
    return f"borrower_{days}"


def due_followups(now, submitted_at, status, sent_kinds):
    """Returns the follow-up kinds to send right now, in order."""
    if submitted_at is None or status not in ACTIVE:
        return []
    sent = set(sent_kinds)
    due = []

    age = now - submitted_at
    week = int(age.total_seconds() // (7 * 86400))     # completed weeks since submission
    if 1 <= week <= MAX_LENDER_WEEKS and lender_kind(week) not in sent:
        due.append(lender_kind(week))

    for d in BORROWER_DAYS:
        start = submitted_at + timedelta(days=d)
        if start <= now < start + timedelta(days=BORROWER_GRACE_DAYS) and borrower_kind(d) not in sent:
            due.append(borrower_kind(d))
    return due
