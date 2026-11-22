"""Admin: create partners, issue/rotate/revoke API keys. Mounted behind require_admin."""
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.security import KEY_MODES, generate_api_key, generate_webhook_secret
from app.engine.urlsafety import is_safe_webhook_url
from app.models.partner import Partner
from app.services.audit_service import log_event
from app.services.crypto_service import encrypt_bytes

router = APIRouter()


class PartnerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    mode: str = "sandbox"
    webhook_url: Optional[str] = None
    revenue_share_pct: Optional[float] = Field(default=None, ge=0, le=100)


class WebhookUpdate(BaseModel):
    webhook_url: Optional[str] = None


def _check_webhook(url):
    if not url:
        return
    ok, reason = is_safe_webhook_url(url, allow_insecure=os.environ.get("ALLOW_INSECURE_WEBHOOKS", "").lower() == "true")
    if not ok:
        raise HTTPException(status_code=422, detail=f"Webhook URL rejected: {reason}")


def _view(p: Partner):
    return {
        "id": p.id, "name": p.name, "mode": p.mode, "active": p.active,
        "api_key_prefix": p.api_key_prefix, "webhook_url": p.webhook_url,
        "revenue_share_pct": p.revenue_share_pct, "created_at": p.created_at, "revoked_at": p.revoked_at,
    }


@router.post("", status_code=201)
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db)):
    if payload.mode not in KEY_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {list(KEY_MODES)}")
    if db.query(Partner).filter(Partner.name == payload.name).first():
        raise HTTPException(status_code=409, detail="A partner with that name already exists")
    _check_webhook(payload.webhook_url)

    key, prefix, key_hash = generate_api_key(payload.mode)
    partner = Partner(
        name=payload.name, mode=payload.mode, api_key_prefix=prefix, api_key_hash=key_hash,
        revenue_share_pct=payload.revenue_share_pct, webhook_url=payload.webhook_url,
    )
    secret = None
    if payload.webhook_url:
        secret = generate_webhook_secret()
        partner.webhook_secret_enc = encrypt_bytes(secret.encode()).decode()
    db.add(partner)
    db.commit()
    db.refresh(partner)
    log_event(db, f"[admin] partner {partner.id} created (mode={partner.mode})")

    out = _view(partner)
    out["api_key"] = key   # shown once; only a hash is stored
    if secret:
        out["webhook_secret"] = secret   # shown once
    return out


@router.get("")
def list_partners(db: Session = Depends(get_db)):
    return {"partners": [_view(p) for p in db.query(Partner).order_by(Partner.id).all()]}


@router.post("/{partner_id}/rotate-key")
def rotate_key(partner_id: int, db: Session = Depends(get_db)):
    p = db.query(Partner).filter(Partner.id == partner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Partner not found")
    key, prefix, key_hash = generate_api_key(p.mode)
    p.api_key_prefix, p.api_key_hash = prefix, key_hash   # old key stops working immediately
    db.commit()
    log_event(db, f"[admin] partner {p.id} API key rotated")
    return {"id": p.id, "api_key": key, "api_key_prefix": prefix}


@router.put("/{partner_id}/webhook")
def set_webhook(partner_id: int, payload: WebhookUpdate, db: Session = Depends(get_db)):
    """Set or clear the webhook URL. Always issues a fresh signing secret when set."""
    p = db.query(Partner).filter(Partner.id == partner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Partner not found")
    _check_webhook(payload.webhook_url)
    p.webhook_url = payload.webhook_url
    secret = None
    if payload.webhook_url:
        secret = generate_webhook_secret()
        p.webhook_secret_enc = encrypt_bytes(secret.encode()).decode()
    else:
        p.webhook_secret_enc = None
    db.commit()
    log_event(db, f"[admin] partner {p.id} webhook {'set' if secret else 'cleared'}")
    out = {"id": p.id, "webhook_url": p.webhook_url}
    if secret:
        out["webhook_secret"] = secret
    return out


@router.post("/{partner_id}/revoke")
def revoke(partner_id: int, db: Session = Depends(get_db)):
    p = db.query(Partner).filter(Partner.id == partner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Partner not found")
    p.active = False
    p.revoked_at = datetime.now(timezone.utc)
    db.commit()
    log_event(db, f"[admin] partner {p.id} revoked")
    return _view(p)
