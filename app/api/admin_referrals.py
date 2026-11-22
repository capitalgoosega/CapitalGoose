"""Admin: view referrals, record lender milestones, webhook health, lending accuracy."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine import statuses as S
from app.engine.metrics import accuracy_summary
from app.engine.referral_service import InvalidTransition, record_status, serialize_referral
from app.models.partner import Referral, WebhookDelivery
from app.services.audit_service import log_event

router = APIRouter()


class StatusUpdate(BaseModel):
    status: str
    detail: Optional[str] = Field(default=None, max_length=500)   # internal note, never sent to partners


@router.get("")
def list_referrals(
    status: Optional[str] = None,
    partner_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    q = db.query(Referral)
    if status:
        q = q.filter(Referral.status == status)
    if partner_id:
        q = q.filter(Referral.partner_id == partner_id)
    rows = q.order_by(Referral.id.desc()).limit(max(1, min(limit, 500))).all()
    return {"referrals": [serialize_referral(db, r, include_internal=True) for r in rows]}


# NOTE: fixed paths must stay above /{public_id}.
@router.get("/metrics/lending-accuracy")
def lending_accuracy(partner_id: Optional[int] = None, db: Session = Depends(get_db)):
    """Funded loans / fully submitted applications (credit pulls and abandoned forms don't count)."""
    def count(*conds):
        q = db.query(func.count(Referral.id)).filter(Referral.submitted_at.isnot(None))
        if partner_id:
            q = q.filter(Referral.partner_id == partner_id)
        for c in conds:
            q = q.filter(c)
        return q.scalar() or 0

    return accuracy_summary(
        submitted=count(),
        funded=count(Referral.status == S.FUNDED),
        declined=count(Referral.status == S.DECLINED),
        withdrawn=count(Referral.status == S.WITHDRAWN),
    )


@router.get("/webhooks/deliveries")
def webhook_deliveries(status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(WebhookDelivery)
    if status:
        q = q.filter(WebhookDelivery.status == status)
    rows = q.order_by(WebhookDelivery.id.desc()).limit(max(1, min(limit, 500))).all()
    return {"deliveries": [
        {"event_id": d.event_id, "partner_id": d.partner_id, "type": d.event_type, "status": d.status,
         "attempts": d.attempts, "last_status_code": d.last_status_code, "last_error": d.last_error,
         "created_at": d.created_at, "delivered_at": d.delivered_at}
        for d in rows
    ]}


@router.post("/webhooks/deliveries/{event_id}/retry")
def retry_delivery(event_id: str, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    d = db.query(WebhookDelivery).filter(WebhookDelivery.event_id == event_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Delivery not found")
    d.status, d.attempts, d.next_attempt_at = "pending", 0, datetime.now(timezone.utc)
    db.commit()
    return {"event_id": d.event_id, "status": d.status}


@router.get("/{public_id}")
def get_referral(public_id: str, db: Session = Depends(get_db)):
    r = db.query(Referral).filter(Referral.public_id == public_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Referral not found")
    return serialize_referral(db, r, include_internal=True)


@router.post("/{public_id}/status")
def update_status(public_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    """Record a lender milestone (submitted, lender_received, approved, closing, funded, declined, withdrawn)."""
    if payload.status not in S.ALL_STATUSES or payload.status in S.ENGINE_ONLY:
        allowed = sorted(S.ALL_STATUSES - S.ENGINE_ONLY)
        raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")
    r = db.query(Referral).filter(Referral.public_id == public_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Referral not found")
    try:
        record_status(db, r, payload.status, detail=payload.detail, source="admin")
    except InvalidTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
    log_event(db, f"[admin] referral {r.public_id} -> {payload.status}")
    return serialize_referral(db, r, include_internal=True)
