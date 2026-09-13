from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from app.db.session import Base


class SoftPullResult(Base):
    """
    Stores the result of a credit soft pull for an application.

    NOTE: `source` is currently always "simulated" — there is no live
    credit bureau integration yet. When a real bureau/API is connected,
    set source to the provider name (e.g. "experian") so simulated and
    real results can always be told apart in the data.
    """
    __tablename__ = "soft_pull_results"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    credit_score = Column(Integer, nullable=False)
    source = Column(String, nullable=False, default="simulated")
    pulled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
