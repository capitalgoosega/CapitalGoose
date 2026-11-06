import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.access_code import DocumentAccessGrant
from app.models.application import Application
from app.models.bank_profile import BankProfile
from app.services.audit_service import log_event
from app.services.document_vault_service import create_access_grant
from app.services.email_service import send_bank_document_access_email

router = APIRouter()


def _status(grant):
    if grant.revoked:
        return "revoked"
    if grant.expires_at and grant.expires_at < datetime.now(timezone.utc):
        return "expired"
    return "active"


def _grant_dict(grant, bank_names):
    return {
        "id": grant.id,
        "application_id": grant.application_id,
        "bank": bank_names.get(grant.bank_profile_id),
        "status": _status(grant),
        "code_hint": "..." + (grant.code or "")[-4:],
        "created_at": grant.created_at,
        "expires_at": grant.expires_at,
        "access_count": grant.access_count,
        "last_accessed_at": grant.last_accessed_at,
    }


def _bank_names(db):
    return {b.id: b.name for b in db.query(BankProfile).all()}


def _get_grant(db, grant_id):
    grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.id == grant_id).first()
    if not grant:
        raise HTTPException(status_code=404, detail="Access grant not found")
    return grant


@router.get("/", tags=["admin-access-grants"])
def list_grants(application_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(DocumentAccessGrant)
    if application_id is not None:
        query = query.filter(DocumentAccessGrant.application_id == application_id)
    grants = query.order_by(DocumentAccessGrant.id.desc()).limit(200).all()
    names = _bank_names(db)
    return {"grants": [_grant_dict(g, names) for g in grants]}


@router.post("/{grant_id}/revoke", tags=["admin-access-grants"])
def revoke_grant_by_id(grant_id: int, db: Session = Depends(get_db)):
    grant = _get_grant(db, grant_id)
    already = bool(grant.revoked)
    if not already:
        grant.revoked = True
        db.commit()
        log_event(db, f"Access grant {grant.id} for application {grant.application_id} revoked by admin")
    result = _grant_dict(grant, _bank_names(db))
    result["already_revoked"] = already
    return result


@router.post("/{grant_id}/regenerate", tags=["admin-access-grants"])
def regenerate_grant(grant_id: int, db: Session = Depends(get_db)):
    old = _get_grant(db, grant_id)

    if old.bank_profile_id is None:
        raise HTTPException(
            status_code=400,
            detail="This grant isn't linked to a lender, so it can't be regenerated. Revoke it instead.",
        )

    bank = db.query(BankProfile).filter(BankProfile.id == old.bank_profile_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Lender not found")
    if not bank.active:
        raise HTTPException(status_code=400, detail="That lender is inactive")

    recipient = bank.contact_email
    redirected = False
    if os.environ.get("TEST_MODE", "").lower() == "true" and os.environ.get("TEST_RECIPIENT_EMAIL"):
        recipient = os.environ["TEST_RECIPIENT_EMAIL"]
        redirected = True
    if not recipient:
        raise HTTPException(status_code=400, detail="That lender has no contact email on file")

    application = db.query(Application).filter(Application.id == old.application_id).first()

    # Turn off every live code for this application and bank.
    live = (
        db.query(DocumentAccessGrant)
        .filter(
            DocumentAccessGrant.application_id == old.application_id,
            DocumentAccessGrant.bank_profile_id == old.bank_profile_id,
            DocumentAccessGrant.revoked.isnot(True),
        )
        .all()
    )
    for g in live:
        g.revoked = True
    db.commit()

    new_grant = create_access_grant(
        db,
        old.application_id,
        recipient,
        recipient_label=bank.name,
        bank_profile_id=bank.id,
    )
    send_bank_document_access_email(
        recipient,
        bank.name,
        new_grant.code,
        application.name if application else "",
    )
    log_event(
        db,
        f"Access grant regenerated for application {old.application_id} ({bank.name}): "
        f"{len(live)} old grant(s) revoked, new grant {new_grant.id} issued",
    )

    result = _grant_dict(new_grant, _bank_names(db))
    result["revoked_grant_ids"] = [g.id for g in live]
    result["sent_to_test_inbox_instead"] = redirected
    return result
