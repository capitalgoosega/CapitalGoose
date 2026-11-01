from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer
from app.db.session import Base


class ApplicationFinancials(Base):
    """
    The financial figures an applicant submitted on Form 2, plus the
    DSCR calculated from them. One row per application.
    """
    __tablename__ = "application_financials"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, nullable=False, index=True)
    years_in_business = Column(Float, nullable=True)
    annual_revenue = Column(Float, nullable=True)
    annual_net_operating_income = Column(Float, nullable=True)
    annual_debt_payments = Column(Float, nullable=True)
    dscr = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
