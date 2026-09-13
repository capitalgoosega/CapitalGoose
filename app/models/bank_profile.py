from sqlalchemy import Column, Integer, String, Boolean
from app.db.session import Base


class BankProfile(Base):
    """
    A queryable lending partner profile.

    NOTE: All rows are currently placeholder/fictional banks used for
    testing the matching logic. Replace with real lending partners and
    their actual criteria once partnerships are in place.
    """
    __tablename__ = "bank_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    contact_email = Column(String, nullable=True)

    min_credit_score = Column(Integer, nullable=False, default=0)
    max_credit_score = Column(Integer, nullable=False, default=850)

    # Comma-separated loan types this bank accepts, e.g. "sba,equipment,general"
    accepted_loan_types = Column(String, nullable=False, default="general")

    active = Column(Boolean, default=True)

    def accepts_loan_type(self, loan_type: str) -> bool:
        types = [t.strip().lower() for t in self.accepted_loan_types.split(",")]
        return loan_type.lower() in types or "general" in types
