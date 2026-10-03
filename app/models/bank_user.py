from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from app.db.session import Base


class BankUser(Base):
    """
    A login account for a banking partner's staff to access the
    secure document portal. Each user belongs to exactly one bank
    (bank_profile_id) and can only ever view collection packages
    assigned to that bank.

    NOTE: accounts are currently created by seeding (see main.py),
    not self-signup. There is no password-reset flow yet — if a bank
    needs a new password, update their row directly for now.
    """
    __tablename__ = "bank_users"

    id = Column(Integer, primary_key=True, index=True)
    bank_profile_id = Column(Integer, ForeignKey("bank_profiles.id"), nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
