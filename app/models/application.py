from sqlalchemy import Column, Integer, String
from app.db.session import Base

class Application(Base):
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    source_entry_id = Column(String, unique=True, index=True, nullable=True)
    name = Column(String)
    email = Column(String)
    loan_amount = Column(Integer)
    loan_type = Column(String)
    credit_score = Column(Integer)
    status = Column(String)
    lender = Column(String, nullable=True)
