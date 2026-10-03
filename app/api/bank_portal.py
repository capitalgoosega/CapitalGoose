from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_user import BankUser
from app.models.bank_profile import BankProfile
from app.services.auth_service import verify_password, create_token

router = APIRouter()


class BankLoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", tags=["bank-portal"])
def bank_login(payload: BankLoginRequest, db: Session = Depends(get_db)):
    user = db.query(BankUser).filter(BankUser.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    bank = db.query(BankProfile).filter(BankProfile.id == user.bank_profile_id).first()
    token = create_token(user.id, user.bank_profile_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "bank_name": bank.name if bank else None,
    }
