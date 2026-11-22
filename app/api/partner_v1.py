"""
Partner-facing headless API. Authenticated with an X-API-Key header.

  POST /v1/referrals         submit an applicant with consent; get a prequalification
  GET  /v1/referrals/{id}    current status and timeline
  GET  /v1/referrals         list your own referrals
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.credit_provider import ProviderNotConfigured
from app.engine.ratelimit import SlidingWindowLimiter
from app.engine.referral_service import EngineUnavailable, create_referral, serialize_referral
from app.engine.security import hash_api_key
from app.models.partner import Partner, Referral
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
