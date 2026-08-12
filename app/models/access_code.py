import secrets
import string
from datetime import datetime, timedelta, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.db.session import Base

def generate_access_code(length: int = 10) -> str:
  # Short, hard-to-guess, easy-to-type-over-the-phone access code.
  alphabet = string.ascii_uppercase + string.digits
  alphabet = alphabet.translate({ord(c): None for c in "0O1IL"})
  return "".join(secrets.choice(alphabet) for _ in range(length))

class DocumentAccessGrant(Base):
  __tablename__ = "document_access_grants"

  id = Column(Integer, primary_key=True, index=True)
  application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
  code = Column(String, unique=True, nullable=False, index=True, default=generate_access_code)
  recipient_email = Column(String, nullable=False)
  recipient_label = Column(String, nullable=True)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
  expires_at = Column(DateTime(timezone=True), nullable=False)
  revoked = Column(Boolean, default=False)
  access_count = Column(Integer, default=0)
  last_accessed_at = Column(DateTime(timezone=True), nullable=True)


  @staticmethod
  def default_expiry(days: int = 7) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)
