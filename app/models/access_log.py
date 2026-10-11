from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String
from app.db.session import Base


class DocumentAccessLog(Base):
    """
    Audit trail of bank access to collection packages. One row per
    event: a bank listing a package's documents, or downloading one.

    Intentionally has no foreign keys: bank rows are rebuilt on every
    deploy, and audit records must never be altered or lost because of
    that. Names and emails are stored as plain text instead.
    """
    __tablename__ = "document_access_log"

    id = Column(Integer, primary_key=True, index=True)
    accessed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    application_id = Column(Integer, nullable=False, index=True)
    grant_id = Column(Integer, nullable=True)
    bank_name = Column(String, nullable=True)
    bank_user_email = Column(String, nullable=True)
    action = Column(String, nullable=False)  # "list" or "download"
    document_id = Column(Integer, nullable=True)
    filename = Column(String, nullable=True)
