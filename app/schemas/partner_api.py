from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.bank_profile import to_state_code


class AddressIn(BaseModel):
    street: str = Field(max_length=200)
    city: str = Field(max_length=100)
    state: str
    zip: str = Field(max_length=10)


class ApplicantIn(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(default=None, max_length=30)
    dob: str                      # YYYY-MM-DD or MM/DD/YYYY; used for the age check and the pull, not stored
    address: AddressIn
    # Only used when the engine runs on self-reported credit ranges.
    credit_band: Optional[str] = Field(default=None, max_length=20)

    @field_validator("credit_band")
    @classmethod
    def _band(cls, v):
        if v is None or v == "":
            return None
        from app.engine.credit_bands import BANDS
        if v not in BANDS:
            raise ValueError("credit_band must be one of: " + ", ".join(BANDS))
        return v


class BusinessIn(BaseModel):
    legal_name: str = Field(min_length=1, max_length=200)
    state: str                    # state the business operates in
    industry: str = Field(default="construction", max_length=60)
    years_in_business: float = Field(ge=0, le=200)
    annual_revenue: float = Field(ge=0)
    annual_net_operating_income: float
    annual_debt_payments: float = Field(ge=0)

    @field_validator("state")
    @classmethod
    def _state(cls, v):
        code = to_state_code(v)
        if not code:
            raise ValueError("unrecognized US state")
        return code


class LoanIn(BaseModel):
    amount: int = Field(gt=0, le=50_000_000)
    type: str = Field(min_length=1, max_length=40)   # e.g. sba_7a, sba_504, equipment, working_capital


class ConsentIn(BaseModel):
    accepted: bool
    signer_name: str = Field(min_length=1, max_length=200)
    consent_version: str = Field(min_length=1, max_length=40)
    captured_at: datetime
    ip_address: Optional[str] = Field(default=None, max_length=64)

    @field_validator("accepted")
    @classmethod
    def _must_accept(cls, v):
        if v is not True:
            raise ValueError("consent must be accepted before any credit data is requested")
        return v


class ReferralCreate(BaseModel):
    external_ref: Optional[str] = Field(default=None, max_length=100)
    applicant: ApplicantIn
    business: BusinessIn
    loan: LoanIn
    consent: ConsentIn
