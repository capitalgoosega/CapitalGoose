from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_profile import BankProfile, GEOGRAPHY_STATUSES, normalize_allowed_states

router = APIRouter()


def _check_states(value):
    return normalize_allowed_states(value)


def _check_status(value):
    if value is not None and value not in GEOGRAPHY_STATUSES:
        raise ValueError(f"geography_status must be one of {sorted(GEOGRAPHY_STATUSES)}")
    return value


class LenderCreate(BaseModel):
    name: str
    contact_email: Optional[EmailStr] = None
    min_credit_score: int = 0
    max_credit_score: int = 850
    allowed_states: Optional[str] = None
    geography_status: Optional[str] = "confirmed"
    verified: bool = False
    cash_flow_requirement: Optional[str] = None
    min_dscr: Optional[float] = None
    min_annual_revenue: Optional[int] = None
    years_in_business_required: Optional[int] = 2
    pfs_required: bool = True
    active: bool = True

    _v_states = field_validator("allowed_states")(lambda cls, v: _check_states(v))
    _v_status = field_validator("geography_status")(lambda cls, v: _check_status(v))


class LenderUpdate(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    min_credit_score: Optional[int] = None
    max_credit_score: Optional[int] = None
    allowed_states: Optional[str] = None
    geography_status: Optional[str] = None
    verified: Optional[bool] = None
    cash_flow_requirement: Optional[str] = None
    min_dscr: Optional[float] = None
    min_annual_revenue: Optional[int] = None
    years_in_business_required: Optional[int] = None
    pfs_required: Optional[bool] = None
    active: Optional[bool] = None

    _v_states = field_validator("allowed_states")(lambda cls, v: _check_states(v))
    _v_status = field_validator("geography_status")(lambda cls, v: _check_status(v))


def lender_to_dict(b: BankProfile):
    return {
        "id": b.id,
        "name": b.name,
        "contact_email": b.contact_email,
        "min_credit_score": b.min_credit_score,
        "max_credit_score": b.max_credit_score,
        "allowed_states": b.allowed_states,
        "geography_status": b.geography_status,
        "verified": b.verified,
        "cash_flow_requirement": b.cash_flow_requirement,
        "min_dscr": b.min_dscr,
        "min_annual_revenue": b.min_annual_revenue,
        "years_in_business_required": b.years_in_business_required,
        "pfs_required": b.pfs_required,
        "active": b.active,
    }


@router.get("/", tags=["admin-lenders"])
def list_lenders(db: Session = Depends(get_db)):
    lenders = db.query(BankProfile).order_by(BankProfile.id).all()
    return {"lenders": [lender_to_dict(b) for b in lenders]}


@router.post("/", tags=["admin-lenders"])
def create_lender(payload: LenderCreate, db: Session = Depends(get_db)):
    if db.query(BankProfile).filter(BankProfile.name == payload.name).first():
        raise HTTPException(status_code=409, detail="A lender with that name already exists")
    lender = BankProfile(**payload.model_dump())
    db.add(lender)
    db.commit()
    db.refresh(lender)
    return lender_to_dict(lender)


@router.patch("/{lender_id}", tags=["admin-lenders"])
def update_lender(lender_id: int, payload: LenderUpdate, db: Session = Depends(get_db)):
    lender = db.query(BankProfile).filter(BankProfile.id == lender_id).first()
    if not lender:
        raise HTTPException(status_code=404, detail="Lender not found")

    changes = payload.model_dump(exclude_unset=True)

    new_name = changes.get("name")
    if new_name and new_name != lender.name:
        if db.query(BankProfile).filter(BankProfile.name == new_name).first():
            raise HTTPException(status_code=409, detail="A lender with that name already exists")

    for field, value in changes.items():
        setattr(lender, field, value)
    db.commit()
    db.refresh(lender)
    return lender_to_dict(lender)
