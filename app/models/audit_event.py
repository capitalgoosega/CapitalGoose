from sqlalchemy import Column, Integer, String
from app.db.session import Base


class AuditEvent(Base):
    __tablename__ = "audit"

    id = Column(Integer, primary_key=True, index=True)

    message = Column(String)
