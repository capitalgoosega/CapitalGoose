"""
Partner-facing headless API. Authenticated with an X-API-Key header.

  POST /v1/referrals         submit an applicant with consent; get a prequalification
  GET  /v1/referrals/{id}    current status and timeline
  GET  /v1/referrals         list your own referrals
"""
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.credit_provider import ProviderNotConfigured
from app.engine.ratelimit import SlidingWindowLimiter
from app.engine.documents import DOC_TYPES, MAX_BYTES, check_upload
from app.engine.handoff_service import HandoffError, document_summary, handoff, store_document
from app.engine.referral_service import EngineUnavailable, create_referral, serialize_referral
from app.engine import statuses as S
from app.engine.consent import consent_text_approved
from app.engine.lender_links import hash_link_token
from app.engine.security import hash_api_key
from app.engine.widget_rules import SESSION_TTL_MINUTES, clean_prefill, valid_origin
from app.models.partner import Partner, Referral, WidgetSession
from app.schemas.partner_api import ReferralCreate

router = APIRouter()

_limiter = SlidingWindowLimiter(limit=120, window_seconds=60)


def require_partner(x_api_key: str = Header(None), db: Session = Depends(get_db)) -> Partner:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    partner = (
        db.query(Partner)
        .filter(Partner.api_key_hash == hash_api_key(x_api_key), Partner.active == True)  # noqa: E712
        .first()
    )
    if not partner:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if not _limiter.allow(partner.id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded (120 requests per minute)")
    return partner


def _client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/referrals", status_code=201, tags=["partner-api"])
def submit_referral(
    payload: ReferralCreate,
    request: Request,
    idempotency_key: Optional[str] = Header(None, max_length=100),
    partner: Partner = Depends(require_partner),
    db: Session = Depends(get_db),
):
    try:
        referral, created = create_referral(
            db, partner, payload, idempotency_key=idempotency_key, partner_ip=_client_ip(request)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EngineUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ProviderNotConfigured:
        raise HTTPException(status_code=503, detail="Credit provider is not available")
    except Exception:
        # Details are in the server log; partners get a retryable error.
        db.rollback()
        raise HTTPException(status_code=502, detail="Could not complete the credit check. Please retry.")
    body = serialize_referral(db, referral)
    body["idempotent_replay"] = not created
    return body


@router.get("/referrals/{referral_id}", tags=["partner-api"])
def get_referral(referral_id: str, partner: Partner = Depends(require_partner), db: Session = Depends(get_db)):
    referral = (
        db.query(Referral)
        .filter(Referral.public_id == referral_id, Referral.partner_id == partner.id)
        .first()
    )
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    return serialize_referral(db, referral)


@router.get("/referrals", tags=["partner-api"])
def list_referrals(
    external_ref: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    partner: Partner = Depends(require_partner),
    db: Session = Depends(get_db),
):
    q = db.query(Referral).filter(Referral.partner_id == partner.id)
    if external_ref:
        q = q.filter(Referral.external_ref == external_ref)
    if status:
        q = q.filter(Referral.status == status)
    rows = q.order_by(Referral.id.desc()).limit(max(1, min(limit, 200))).all()
    return {"referrals": [serialize_referral(db, r) for r in rows]}


def _own_referral(db, partner, referral_id):
    referral = (
        db.query(Referral)
        .filter(Referral.public_id == referral_id, Referral.partner_id == partner.id)
        .first()
    )
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")
    return referral


@router.put("/referrals/{referral_id}/documents/{doc_type}", status_code=201, tags=["partner-api"])
async def upload_document(
    referral_id: str,
    doc_type: str,
    request: Request,
    filename: str,
    partner: Partner = Depends(require_partner),
    db: Session = Depends(get_db),
):
    """Raw file bytes in the request body (PDF, PNG or JPEG, up to 15 MB)."""
    referral = _own_referral(db, partner, referral_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=422, detail=f"doc_type must be one of {sorted(DOC_TYPES)}")
    if referral.status != S.PREQUALIFIED:
        raise HTTPException(status_code=409, detail="Documents can only be added to a prequalified referral")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 15 MB")
    data = await request.body()
    content_type, err_status, err_msg = check_upload(data)
    if err_status:
        raise HTTPException(status_code=err_status, detail=err_msg)
    try:
        blob = store_document(db, referral, doc_type, filename, data, content_type)
    except HandoffError as e:
        raise HTTPException(status_code=409, detail=str(e))
    summary = document_summary(db, referral)
    return {"document_id": blob.id, "doc_type": doc_type, "missing": summary["missing"]}


@router.get("/referrals/{referral_id}/documents", tags=["partner-api"])
def list_referral_documents(referral_id: str, partner: Partner = Depends(require_partner), db: Session = Depends(get_db)):
    return document_summary(db, _own_referral(db, partner, referral_id))


@router.post("/referrals/{referral_id}/submit", tags=["partner-api"])
def submit_to_lender(referral_id: str, partner: Partner = Depends(require_partner), db: Session = Depends(get_db)):
    """Tell us the file is complete. We hand it to the matched lender and track it from here."""
    referral = _own_referral(db, partner, referral_id)
    if referral.status in S.FORWARD_PATH and S.FORWARD_PATH.index(referral.status) >= S.FORWARD_PATH.index(S.SUBMITTED):
        # Already handed off (or further along): safe to call twice.
        body = serialize_referral(db, referral)
        body["idempotent_replay"] = True
        return body
    try:
        handoff(db, referral)
    except HandoffError as e:
        raise HTTPException(status_code=409 if "Missing" not in str(e) else 422, detail=str(e))
    return serialize_referral(db, referral)


class WidgetSessionCreate(BaseModel):
    external_ref: Optional[str] = Field(default=None, max_length=100)
    allowed_origin: Optional[str] = Field(default=None, max_length=200)   # e.g. https://app.partner.com
    prefill: dict = Field(default_factory=dict)


@router.post("/widget-sessions", status_code=201, tags=["partner-api"])
def create_widget_session(
    payload: WidgetSessionCreate,
    partner: Partner = Depends(require_partner),
    db: Session = Depends(get_db),
):
    """
    Call this from YOUR server. Give the returned `token` to the applicant's browser
    (iframe src = embed_url). It works once, for 30 minutes, and carries no API key.
    """
    import secrets
    if partner.mode == "live" and not consent_text_approved():
        raise HTTPException(status_code=503, detail="The hosted form's consent wording is awaiting legal approval, so live sessions are disabled")
    allow_local = partner.mode != "live"
    if payload.allowed_origin and not valid_origin(payload.allowed_origin, allow_local=allow_local):
        raise HTTPException(status_code=422, detail="allowed_origin must be an exact https origin like https://app.example.com")
    prefill, err = clean_prefill(payload.prefill)
    if err:
        raise HTTPException(status_code=422, detail=err)

    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
    db.add(WidgetSession(
        partner_id=partner.id, token_hash=hash_link_token(token), external_ref=payload.external_ref,
        allowed_origin=payload.allowed_origin, prefill_json=json.dumps(prefill), expires_at=expires,
    ))
    db.commit()
    base = os.environ.get("APP_BASE_URL", "https://capitalgoose-production.up.railway.app").rstrip("/")
    return {"token": token, "expires_at": expires, "embed_url": f"{base}/widget/{token}", "script_url": f"{base}/widget/embed.js"}
