import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_profile import BankProfile
from app.models.bank_user import BankUser
from app.services.auth_service import generate_invite_token, hash_invite_token
from app.services.email_service import send_bank_invitation_email

router = APIRouter()

INVITE_TTL_HOURS = int(os.environ.get("INVITE_TTL_HOURS", 72))
PORTAL_BASE_URL = os.environ.get("PORTAL_BASE_URL", "https://capitalgoose-production.up.railway.app")


class InviteRequest(BaseModel):
    bank_profile_id: int
    email: EmailStr
    reissue: bool = False  # true = reset an existing active user's password and MFA


@router.post("/invite", tags=["admin-bank-users"])
def invite_bank_user(payload: InviteRequest, db: Session = Depends(get_db)):
    bank = db.query(BankProfile).filter(BankProfile.id == payload.bank_profile_id).first()
    if not bank:
        raise HTTPException(status_code=404, detail="Lender not found")

    email = payload.email.lower()
    user = db.query(BankUser).filter(BankUser.email == email).first()

    if user and user.bank_profile_id != bank.id:
        raise HTTPException(status_code=409, detail="That email already belongs to a different lender")
    if user and user.status == "active" and not payload.reissue:
        raise HTTPException(status_code=409, detail="That user is already active. Set reissue=true to reset their password and MFA.")

    token = generate_invite_token()
    if not user:
        user = BankUser(bank_profile_id=bank.id, email=email)
        db.add(user)

    user.status = "invited"
    user.password_hash = None
    user.mfa_secret_enc = None
    user.mfa_enabled = False
    user.mfa_last_step = None
    user.failed_attempts = 0
    user.locked_until = None
    user.invite_token_hash = hash_invite_token(token)
    user.invite_expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)
    db.commit()
    db.refresh(user)

    activation_url = f"{PORTAL_BASE_URL}/bank-portal/activate#t={token}"

    # TEST MODE: send the invitation to a safe test inbox, not the bank contact.
    deliver_to = email
    redirected = False
    if os.environ.get("TEST_MODE", "").lower() == "true" and os.environ.get("TEST_RECIPIENT_EMAIL"):
        deliver_to = os.environ["TEST_RECIPIENT_EMAIL"]
        redirected = True

    send_bank_invitation_email(deliver_to, activation_url, bank.name, INVITE_TTL_HOURS)

    return {
        "user_id": user.id,
        "email": user.email,
        "bank": bank.name,
        "status": user.status,
        "invite_expires_at": user.invite_expires_at,
        "sent_to_test_inbox_instead": redirected,
    }


@router.get("/", tags=["admin-bank-users"])
def list_bank_users(db: Session = Depends(get_db)):
    names = {b.id: b.name for b in db.query(BankProfile).all()}
    users = db.query(BankUser).order_by(BankUser.id).all()
    return {
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "bank": names.get(u.bank_profile_id),
                "status": u.status,
                "mfa_enabled": u.mfa_enabled,
                "last_login_at": u.last_login_at,
                "invite_expires_at": u.invite_expires_at,
            }
            for u in users
        ]
    }


@router.post("/{user_id}/disable", tags=["admin-bank-users"])
def disable_bank_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(BankUser).filter(BankUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.status = "disabled"
    user.invite_token_hash = None
    user.invite_expires_at = None
    db.commit()
    return {"id": user.id, "email": user.email, "status": user.status}
