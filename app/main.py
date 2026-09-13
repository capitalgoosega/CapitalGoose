from fastapi import FastAPI

from app.api.routes import router

from app.db.session import Base, engine, SessionLocal
from app.models.bank_profile import BankProfile


Base.metadata.create_all(bind=engine)


def seed_placeholder_banks():
    """
    One-time seed for testing the bank matching logic. These are
    PLACEHOLDER banks, not real lending partners. Replace or remove
    once real partners are onboarded.
    """
    db = SessionLocal()
    try:
        if db.query(BankProfile).count() > 0:
            return  # already seeded, don't duplicate rows

        placeholder_banks = [
            BankProfile(
                name="Prime National Bank (placeholder)",
                contact_email="amberturner419@gmail.com",
                min_credit_score=750,
                max_credit_score=850,
                accepted_loan_types="general,sba,equipment",
                active=True,
            ),
            BankProfile(
                name="SBA Bank (placeholder)",
                contact_email="amberturner419@gmail.com",
                min_credit_score=650,
                max_credit_score=849,
                accepted_loan_types="sba",
                active=True,
            ),
            BankProfile(
                name="Equipment Finance Group (placeholder)",
                contact_email=None,
                min_credit_score=620,
                max_credit_score=849,
                accepted_loan_types="equipment",
                active=True,
            ),
            BankProfile(
                name="Advance Lender (placeholder)",
                contact_email=None,
                min_credit_score=580,
                max_credit_score=849,
                accepted_loan_types="general,sba,equipment",
                active=True,
            ),
        ]
        db.add_all(placeholder_banks)
        db.commit()
    finally:
        db.close()


seed_placeholder_banks()


app = FastAPI(
    title="Capitol Goose Fintech API",
    version="1.0.0"
)


app.include_router(router)


@app.get("/")
def root():
    return {
        "message": "Capitol Goose Programmatic Underwriting API Running"
    }
