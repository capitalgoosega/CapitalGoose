from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router

from app.db.session import Base, engine, SessionLocal
from app.models.bank_profile import BankProfile
from app.models.bank_user import BankUser
from app.services.auth_service import hash_password


with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS bank_users CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS bank_profiles CASCADE"))
    conn.commit()

with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE document_access_grants "
        "ADD COLUMN IF NOT EXISTS bank_profile_id INTEGER"
    ))
    conn.commit()

Base.metadata.create_all(bind=engine)


def seed_bank_profiles():
    db = SessionLocal()
    try:
        db.query(BankProfile).delete()

        banks = [
            BankProfile(
                name="AFN (Advance Financial)",
                contact_email="eberry@afnllc.com",
                min_credit_score=650,
                max_credit_score=850,
                geographic_scope="nationwide",
                verified=True,
                cash_flow_requirement="$100K revenue min, $200K preferred",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
            BankProfile(
                name="Celtic Bank",
                contact_email="BSmith@celticbank.com",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="nationwide",
                verified=False,
                cash_flow_requirement="DSCR 1.20x",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
            BankProfile(
                name="KeyBank",
                contact_email=None,
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="tri_state",
                verified=False,
                cash_flow_requirement="DSCR 1.15x",
                years_in_business_required=2,
                pfs_required=True,
                active=False,
            ),
            BankProfile(
                name="TD Bank",
                contact_email=None,
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="tri_state",
                verified=False,
                cash_flow_requirement="DSCR 1.15x",
                years_in_business_required=2,
                pfs_required=True,
                active=False,
            ),
            BankProfile(
                name="Scale Bank",
                contact_email="ann.franklin@scale.bank",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="nationwide",
                verified=False,
                cash_flow_requirement="DSCR 1.25x",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
            BankProfile(
                name="United Midwest",
                contact_email="loanservicing@umwsb.com",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="nationwide",
                verified=False,
                cash_flow_requirement="DSCR 1.20x",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
            BankProfile(
                name="South State Bank",
                contact_email="ddwarika@southstatebank.com",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="georgia",
                verified=False,
                cash_flow_requirement="DSCR 1.25x",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
            BankProfile(
                name="HTB",
                contact_email="brian.moon@htb.com",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="south_east",
                verified=False,
                cash_flow_requirement="DSCR 1.25x",
                years_in_business_required=2,
                pfs_required=True,
                active=True,
            ),
        ]
        db.add_all(banks)
        db.commit()
    finally:
        db.close()


def seed_bank_users():
    TEMP_BANK_PASSWORD = "ChangeMe-CapitalGoose-2026"

    db = SessionLocal()
    try:
        db.query(BankUser).delete()

        banks = db.query(BankProfile).filter(
            BankProfile.active == True,  # noqa: E712
            BankProfile.contact_email.isnot(None),
        ).all()

        for bank in banks:
            db.add(BankUser(
                bank_profile_id=bank.id,
                email=bank.contact_email,
                password_hash=hash_password(TEMP_BANK_PASSWORD),
            ))
        db.commit()
    finally:
        db.close()


seed_bank_profiles()
seed_bank_users()


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
