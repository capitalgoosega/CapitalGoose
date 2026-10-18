from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from app.db.session import Base


class BankUser(Base):
    """
    A login for a banking partner's staff. Created by invitation only.
    status: invited -> active (after the user sets a password and
    confirms MFA), or disabled. Each user belongs to exactly one bank.
    """
    __tablename__ = "bank_users"

    id = Column(Integer, primary_key=True, index=True)
    bank_profile_id = Column(Integer, ForeignKey("bank_profiles.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)
    status = Column(String, nullable=False, default="invited")

    invite_token_hash = Column(String, nullable=True, index=True)
    invite_expires_at = Column(DateTime(timezone=True), nullable=True)

    mfa_secret_enc = Column(String, nullable=True)
    mfa_enabled = Column(Boolean, default=False)
    mfa_last_step = Column(Integer, nullable=True)

    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
