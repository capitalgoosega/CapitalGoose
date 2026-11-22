"""
Sends the lender reminders and borrower check-ins that followups.py says are due.
Runs hourly in a background thread; can also be triggered by an admin.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.engine.followups import ACTIVE, due_followups
from app.engine.handoff_service import HandoffError, _base_url, resolve_recipient
from app.engine.lender_links import LINK_TTL_DAYS, new_link_token
from app.models.application import Application
from app.models.bank_profile import BankProfile
from app.models.partner import FollowUp, LenderStatusLink, Referral
from app.services.audit_service import log_event
from app.services.email_service import send_borrower_checkin_email, send_lender_reminder_email

log = logging.getLogger("followups")
CHECKIN_LINK_DAYS = 30


def _aware(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _send_one(db, referral, kind):
    """Records the follow-up FIRST (unique per referral+kind), then emails. At most once."""
    now = datetime.now(timezone.utc)
    app_row = db.query(Application).filter(Application.id == referral.application_id).first()
    lender = db.query(BankProfile).filter(BankProfile.name == referral.lender_name).first() if referral.lender_name else None
    if not lender:
        return False

    if kind.startswith("lender_w"):
        weeks = int(kind[len("lender_w"):])
        recipient, suppress = resolve_recipient(db, referral, lender.contact_email, lender.name)
        token, token_hash = new_link_token()
        row = FollowUp(referral_id=referral.id, kind=kind, suppressed=suppress)
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False
        # An extra link; earlier links stay valid so an old email still works.
        db.add(LenderStatusLink(
            referral_id=referral.id, bank_profile_id=lender.id, token_hash=token_hash,
            expires_at=now + timedelta(days=LINK_TTL_DAYS),
        ))
        db.commit()
        if not suppress:
            send_lender_reminder_email(recipient, lender.name, referral.public_id, f"{_base_url()}/lender-status/{token}", weeks)
        log_event(db, f"[followup] {kind} for referral {referral.public_id}")
        return True

    days = int(kind.split("_")[1])
    recipient, suppress = resolve_recipient(db, referral, app_row.email if app_row else None, "the applicant")
    token, token_hash = new_link_token()
    row = FollowUp(referral_id=referral.id, kind=kind, token_hash=token_hash, suppressed=suppress)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    if not suppress:
        first = (app_row.name or "there").split(" ")[0] if app_row else "there"
        send_borrower_checkin_email(recipient, first, lender.name, f"{_base_url()}/checkin/{token}", days)
    log_event(db, f"[followup] {kind} for referral {referral.public_id}")
    return True


def run_due(db, now=None):
    """Returns how many follow-ups were sent."""
    now = now or datetime.now(timezone.utc)
    sent = 0
    referrals = (
        db.query(Referral)
        .filter(Referral.status.in_(list(ACTIVE)), Referral.submitted_at.isnot(None))
        .all()
    )
    for ref in referrals:
        try:
            kinds_sent = [k for (k,) in db.query(FollowUp.kind).filter(FollowUp.referral_id == ref.id).all()]
            for kind in due_followups(now, _aware(ref.submitted_at), ref.status, kinds_sent):
                if _send_one(db, ref, kind):
                    sent += 1
        except HandoffError as e:
            db.rollback()
            log.warning("followup skipped for %s: %s", ref.public_id, e)
        except Exception:
            db.rollback()
            log.exception("followup error for %s", ref.public_id)
    return sent


def start_worker(session_factory, interval_seconds=3600):
    """Hourly loop started at boot. Disable with DISABLE_FOLLOWUPS=1."""
    import os
    if os.environ.get("DISABLE_FOLLOWUPS") == "1":
        return None

    def loop():
        time.sleep(60)   # let the app finish booting
        while True:
            try:
                db = session_factory()
                try:
                    run_due(db)
                finally:
                    db.close()
            except Exception:
                log.exception("followup worker error")
            time.sleep(interval_seconds)

    t = threading.Thread(target=loop, name="followup-worker", daemon=True)
    t.start()
    return t
