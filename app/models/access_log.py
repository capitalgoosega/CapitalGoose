from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String
from app.db.session import Base


class DocumentAccessLog(Base):
    """
    Audit trail of bank access to collection packages. One row per
    event: a bank listing a package's documents or downloading one
    (outcome "success"), or an attempt that was refused (outcome
    "blocked", with a reason).

    Intentionally has no foreign keys: bank rows can change, and audit
    records must never be altered or lost because of that. Names and
    emails are stored as plain text instead. Only the last four
    characters of an attempted access code are kept.
    """
    __tablename__ = "document_access_log"

    id = Column(Integer, primary_key=True, index=True)
    accessed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    application_id = Column(Integer, nullable=True, index=True)  # blank when the code doesn't exist
    grant_id = Column(Integer, nullable=True)
    bank_name = Column(String, nullable=True)
    bank_user_email = Column(String, nullable=True)
    action = Column(String, nullable=False)  # "list", "download" or "access"
    document_id = Column(Integer, nullable=True)
    filename = Column(String, nullable=True)
    outcome = Column(String, nullable=True, default="success")  # "success" or "blocked"; older rows are blank
    reason = Column(String, nullable=True)
    code_hint = Column(String, nullable=True)
