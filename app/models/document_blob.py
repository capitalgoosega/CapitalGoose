from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String

from app.db.session import Base

class DocumentBlob(Base):
  __tablename__ = "document_blobs"

  id = Column(Integer, primary_key=True, index=True)
  application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
  filename = Column(String, nullable=False)
  content_type = Column(String, nullable=True)
  content = Column(LargeBinary, nullable=False)
  created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
