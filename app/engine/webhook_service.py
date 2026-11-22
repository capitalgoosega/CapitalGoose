"""
Outbound partner webhooks: queued in the database, signed, retried with backoff.

Payloads carry ids and status only (no applicant details), so a leaked or
misrouted webhook exposes nothing sensitive.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

from app.engine.security import new_public_id, sign_webhook
from app.engine.urlsafety import is_safe_webhook_url
from app.models.partner import Partner, WebhookDelivery
from app.services.crypto_service import decrypt_bytes

log = logging.getLogger("capitalgoose.webhooks")

BACKOFF_SECONDS = [60, 300, 1800, 7200, 43200]   # then give up (6 attempts total)
LEASE_SECONDS = 120


def _now():
    return datetime.now(timezone.utc)


def _allow_insecure():
    return os.environ.get("ALLOW_INSECURE_WEBHOOKS", "").lower() == "true"


def enqueue_event(db, partner, referral, event_type, extra=None):
    """Queue a webhook for the partner, if it has one configured."""
    if not partner or not partner.webhook_url or not partner.webhook_secret_enc:
        return None
    event_id = new_public_id("evt")
    data = {
        "referral_id": referral.public_id,
        "external_ref": referral.external_ref,
        "status": referral.status,
    }
    if extra:
        data.update(extra)
    payload = {
        "id": event_id,
        "type": event_type,
        "created_at": _now().isoformat(),
        "data": data,
    }
    delivery = WebhookDelivery(
        event_id=event_id,
        partner_id=partner.id,
        referral_id=referral.id,
        event_type=event_type,
        payload=json.dumps(payload, separators=(",", ":")),
    )
    db.add(delivery)
    db.commit()
    return delivery


def _send(partner, delivery):
    """Returns (status_code_or_None, error_or_None)."""
    ok, reason = is_safe_webhook_url(partner.webhook_url, allow_insecure=_allow_insecure())
    if not ok:
        return None, f"blocked: {reason}"
    secret = decrypt_bytes(partner.webhook_secret_enc.encode()).decode()
    body = delivery.payload.encode()
    try:
        resp = requests.post(
            partner.webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "CapitalGoose-Webhooks/1",
                "X-CapitalGoose-Event": delivery.event_type,
                "X-CapitalGoose-Signature": sign_webhook(secret, body),
            },
            timeout=10,
            allow_redirects=False,   # a redirect could point somewhere we never vetted
        )
        return resp.status_code, None
    except requests.RequestException as e:
        return None, type(e).__name__


def deliver_due(db, limit=25):
    """Attempts every due delivery once. Returns how many were attempted."""
    due = (
        db.query(WebhookDelivery)
        .filter(WebhookDelivery.status == "pending", WebhookDelivery.next_attempt_at <= _now())
        .order_by(WebhookDelivery.id)
        .limit(limit)
        .all()
    )
    for d in due:
        # Lease the row first so a second worker/replica skips it meanwhile.
        d.next_attempt_at = _now() + timedelta(seconds=LEASE_SECONDS)
        db.commit()

        partner = db.query(Partner).filter(Partner.id == d.partner_id).first()
        if not partner or not partner.active or not partner.webhook_url:
            d.status, d.last_error = "failed", "partner inactive or webhook removed"
            db.commit()
            continue

        code, error = _send(partner, d)
        d.attempts += 1
        d.last_status_code, d.last_error = code, error
        if code is not None and 200 <= code < 300:
            d.status, d.delivered_at, d.last_error = "delivered", _now(), None
        elif d.attempts > len(BACKOFF_SECONDS):
            d.status = "failed"
        else:
            d.next_attempt_at = _now() + timedelta(seconds=BACKOFF_SECONDS[d.attempts - 1])
        db.commit()
    return len(due)


def start_worker(session_factory, interval_seconds=20):
    """Background loop started once at boot. Disable with DISABLE_WEBHOOK_WORKER=1."""
    if os.environ.get("DISABLE_WEBHOOK_WORKER") == "1":
        return None

    def loop():
        while True:
            try:
                db = session_factory()
                try:
                    deliver_due(db)
                finally:
                    db.close()
            except Exception:  # never let the worker die
                log.exception("webhook worker error")
            time.sleep(interval_seconds)

    t = threading.Thread(target=loop, name="webhook-worker", daemon=True)
    t.start()
    return t
