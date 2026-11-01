from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from app.db.session import Base


class LenderEligibilityResult(Base):
    """
    Why an application did or didn't qualify with each lender. One row
    per application and lender. `details` is a JSON list of the
    individual checks (credit score, state, years, revenue, DSCR, PFS).
    """
    __tablename__ = "lender_eligibility_results"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, nullable=False, index=True)
    lender_id = Column(Integer, nullable=True)
    lender_name = Column(String, nullable=False)
    eligible = Column(Boolean, nullable=False, default=False)
    details = Column(Text, nullable=True)
    evaluated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
