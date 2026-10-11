from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router

from app.db.session import Base, engine, SessionLocal
from app.models.bank_profile import BankProfile
from app.models.bank_user import BankUser
from app.services.auth_service import hash_password


# bank_users and bank_profiles are reference/seed data rebuilt on every
# startup. bank_users must be dropped first because it has a foreign key
# pointing at bank_profiles.
with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS bank_users CASCADE"))
    conn.execute(text("DROP TABLE IF EXISTS bank_profiles CASCADE"))
    conn.commit()

# document_access_grants may hold real grant history, so it is never
# dropped. Just add the new column if it is missing.
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE document_access_grants "
        "ADD COLUMN IF NOT EXISTS bank_profile_id INTEGER"
    ))
    conn.commit()

Base.metadata.create_all(bind=engine)


def seed_bank_profiles():
    """
    Seeds BankProfile from the Banking Partner Requirements mapping
    table (Karon, CTO). Replaces any existing rows on every startup so
    this stays in sync with the code below.

    KeyBank and TD Bank are seeded inactive (active=False) because no
    contact email has been provided for them yet.

    Scale Bank is seeded as "nationwide" per the sheet's Geo column,
    though the sheet's notes flag this as unconfirmed.
    """
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
                active=False,  # no email yet, inactive until provided
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
                active=False,  # no email yet, inactive until provided
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
    """
    Creates one login per active bank with a contact email, using the
    unique per-bank passwords stored in the BANK_PASSWORDS Railway
    variable (JSON of {email: password}). Banks with no entry get NO
    login. There is intentionally no shared fallback password.
    """
    import json
    import os

    try:
        passwords = {
            email.lower(): pw
            for email, pw in json.loads(os.environ.get("BANK_PASSWORDS", "{}")).items()
        }
    except Exception as e:
        print(f"BANK_PASSWORDS IS INVALID JSON, no bank logins will be created: {e}")
        passwords = {}

    db = SessionLocal()
    try:
        db.query(BankUser).delete()

        banks = db.query(BankProfile).filter(
            BankProfile.active == True,  # noqa: E712
            BankProfile.contact_email.isnot(None),
        ).all()

        for bank in banks:
            email = bank.contact_email.lower()
            pw = passwords.get(email)
            if not pw:
                print(f"BANK LOGIN SKIPPED (no password set): {email}")
                continue
            db.add(BankUser(
                bank_profile_id=bank.id,
                email=email,
                password_hash=hash_password(pw),
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
