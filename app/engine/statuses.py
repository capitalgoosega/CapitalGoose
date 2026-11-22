"""
Referral lifecycle. One referral = one applicant routed to one lender.

received -> prequalified -> submitted -> lender_received -> approved -> closing -> funded
Side exits: no_match (nothing fit), declined (age check or lender decline),
withdrawn (applicant or partner pulled out).
"""

RECEIVED = "received"
PREQUALIFIED = "prequalified"
NO_MATCH = "no_match"
SUBMITTED = "submitted"            # fully submitted to the lender
LENDER_RECEIVED = "lender_received"
APPROVED = "approved"
CLOSING = "closing"
FUNDED = "funded"
DECLINED = "declined"
WITHDRAWN = "withdrawn"

# The forward path. A status may jump ahead (e.g. submitted -> approved when
# the lender never sent a separate "received" notice) but never backwards.
FORWARD_PATH = [RECEIVED, PREQUALIFIED, SUBMITTED, LENDER_RECEIVED, APPROVED, CLOSING, FUNDED]
TERMINAL = {FUNDED, DECLINED, WITHDRAWN, NO_MATCH}
ALL_STATUSES = set(FORWARD_PATH) | TERMINAL

# Statuses the engine itself sets while prequalifying (never from the admin endpoint).
ENGINE_ONLY = {RECEIVED, PREQUALIFIED, NO_MATCH}

# What Application.status holds for the older Cognito-era code paths.
APPLICATION_STATUS = {
    PREQUALIFIED: "pre_approved",
    NO_MATCH: "no_lender_match",
    SUBMITTED: "submitted",
    DECLINED: "declined",
}


def can_transition(current: str, new: str) -> bool:
    if current not in ALL_STATUSES or new not in ALL_STATUSES:
        return False
    if current in TERMINAL:
        return False
    if new in (DECLINED, WITHDRAWN):
        return True
    if new == NO_MATCH:
        return current == RECEIVED
    if new not in FORWARD_PATH or current not in FORWARD_PATH:
        return False
    return FORWARD_PATH.index(new) > FORWARD_PATH.index(current)
