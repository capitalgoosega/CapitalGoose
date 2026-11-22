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
from app.models.bank_profile import BankProfile
from app.models.application_financials import ApplicationFinancials
from app.models.partner import BorrowerCheckin, Partner, Referral, StatusEvent, WebhookDelivery
from app.models.soft_pull_result import SoftPullResult
from app.engine.handoff_service import HandoffError, send_handoff
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
@router.post("/followups/run")
def run_followups(db: Session = Depends(get_db)):
    """Send any due lender reminders and borrower check-ins now (the hourly worker does this too)."""
    from app.engine.followup_service import run_due
    return {"sent": run_due(db)}


@router.get("/checkins/list")
def list_checkins(limit: int = 100, db: Session = Depends(get_db)):
    """Borrowers' one-tap answers, newest first."""
    rows = (
        db.query(BorrowerCheckin, Referral)
        .join(Referral, Referral.id == BorrowerCheckin.referral_id)
        .order_by(BorrowerCheckin.id.desc()).limit(max(1, min(limit, 500))).all()
    )
    return {"checkins": [
        {"referral_id": r.public_id, "status": r.status, "lender": r.lender_name, "answer": c.answer, "at": c.created_at}
        for c, r in rows
    ]}


def _real_referrals(db, include_sandbox):
    """Sandbox partners use practice data; by default they never count toward real numbers."""
    q = db.query(Referral)
    if not include_sandbox:
        q = q.join(Partner, Partner.id == Referral.partner_id).filter(Partner.mode == "live")
    return q


@router.get("/metrics/lending-accuracy")
def lending_accuracy(partner_id: Optional[int] = None, include_sandbox: bool = False, db: Session = Depends(get_db)):
    """Funded loans / fully submitted applications (credit pulls and abandoned forms don't count).
    Live partners only unless include_sandbox=true."""
    def count(*conds):
        q = _real_referrals(db, include_sandbox).filter(Referral.submitted_at.isnot(None))
        if partner_id:
            q = q.filter(Referral.partner_id == partner_id)
        for c in conds:
            q = q.filter(c)
        return q.count()

    out = accuracy_summary(
        submitted=count(),
        funded=count(Referral.status == S.FUNDED),
        declined=count(Referral.status == S.DECLINED),
        withdrawn=count(Referral.status == S.WITHDRAWN),
    )
    # Why lenders say no: the raw material for improving the lender rules.
    reasons = (
        _real_referrals(db, include_sandbox)
        .join(StatusEvent, StatusEvent.referral_id == Referral.id)
        .filter(StatusEvent.status == S.DECLINED, StatusEvent.source == "lender")
        .with_entities(StatusEvent.reason_code, func.count(StatusEvent.id))
        .group_by(StatusEvent.reason_code)
        .all()
    )
    out["decline_reasons"] = {(code or "unspecified"): n for code, n in reasons}
    out["includes_sandbox"] = include_sandbox
    return out


@router.get("/outcomes/export")
def export_outcomes(include_sandbox: bool = False, limit: int = 5000, db: Session = Depends(get_db)):
    """
    De-identified training rows for the in-house decision model: one per fully submitted
    referral. No names, emails, addresses, dates of birth or free-text notes. Live partners
    only unless include_sandbox=true. Fine to hand to an AI model; do not add identifiers here.
    """
    refs = (
        _real_referrals(db, include_sandbox)
        .filter(Referral.submitted_at.isnot(None))
        .order_by(Referral.id).limit(max(1, min(limit, 20000))).all()
    )
    rows = []
    for r in refs:
        fin = db.query(ApplicationFinancials).filter(ApplicationFinancials.application_id == r.application_id).first()
        pull = db.query(SoftPullResult).filter(SoftPullResult.application_id == r.application_id).order_by(SoftPullResult.id.desc()).first()
        decline = (
            db.query(StatusEvent)
            .filter(StatusEvent.referral_id == r.id, StatusEvent.status == S.DECLINED, StatusEvent.source == "lender")
            .order_by(StatusEvent.id.desc()).first()
        )
        rows.append({
            "ref": r.public_id,
            "lender": r.lender_name,
            "industry": r.industry,
            "state": r.business_state,
            "credit_score": pull.credit_score if pull else None,
            "credit_basis": pull.source if pull else None,
            "years_in_business": fin.years_in_business if fin else None,
            "annual_revenue": fin.annual_revenue if fin else None,
            "annual_net_operating_income": fin.annual_net_operating_income if fin else None,
            "annual_debt_payments": fin.annual_debt_payments if fin else None,
            "dscr": fin.dscr if fin else None,
            "outcome": r.status,
            "funded": r.status == S.FUNDED,
            "decline_reason_code": decline.reason_code if decline else None,
            "submitted_at": r.submitted_at,
            "closed_at": r.funded_at or r.declined_at or r.withdrawn_at,
        })
    return {"count": len(rows), "includes_sandbox": include_sandbox, "rows": rows}


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


@router.post("/{public_id}/resend-handoff")
def resend_handoff(public_id: str, db: Session = Depends(get_db)):
    """Issues a fresh access code + status link and re-emails the lender (old ones are revoked)."""
    r = db.query(Referral).filter(Referral.public_id == public_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Referral not found")
    if r.status not in (S.SUBMITTED, S.LENDER_RECEIVED, S.APPROVED, S.CLOSING):
        raise HTTPException(status_code=409, detail=f"Nothing to resend while the referral is '{r.status}'")
    lender = db.query(BankProfile).filter(BankProfile.name == r.lender_name).first()
    if not lender:
        raise HTTPException(status_code=409, detail="Matched lender no longer exists")
    try:
        send_handoff(db, r, lender)
    except HandoffError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"referral_id": r.public_id, "resent_to": lender.name}


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
