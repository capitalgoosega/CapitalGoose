from fastapi import FastAPI
from sqlalchemy import text

from app.api.routes import router

from app.db.session import Base, engine, SessionLocal
from app.models.bank_profile import BankProfile
from app.models.bank_user import BankUser
from app.services.auth_service import hash_password


# One-time additive migrations. Safe to run on every startup.
# Lender data is no longer wiped on deploy.
with engine.connect() as conn:
    conn.execute(text("ALTER TABLE IF EXISTS document_access_grants ADD COLUMN IF NOT EXISTS bank_profile_id INTEGER"))
    conn.execute(text("ALTER TABLE IF EXISTS bank_profiles ADD COLUMN IF NOT EXISTS allowed_states VARCHAR"))
    conn.execute(text("ALTER TABLE IF EXISTS bank_profiles ADD COLUMN IF NOT EXISTS geography_status VARCHAR"))
    conn.execute(text("ALTER TABLE IF EXISTS bank_profiles ADD COLUMN IF NOT EXISTS min_dscr DOUBLE PRECISION"))
    conn.execute(text("ALTER TABLE IF EXISTS bank_profiles ADD COLUMN IF NOT EXISTS min_annual_revenue INTEGER"))
    conn.execute(text("ALTER TABLE IF EXISTS bank_profiles DROP COLUMN IF EXISTS geographic_scope"))
    conn.commit()

Base.metadata.create_all(bind=engine)


# Starting lender data, from the Banking Partner Requirements sheet and
# Karon's follow-up answers. The seed only ADDS missing lenders and fills
# blank fields. It never overwrites a value already set, so edits made
# through /admin/lenders survive redeploys.
#
# allowed_states: "ALL" = nationwide, "MN" or "GA,FL" = those states,
# None = unknown (never matches until filled in).
SEED_LENDERS = [
    dict(
        name="AFN (Advance Financial)",
        contact_email="eberry@afnllc.com",
        min_credit_score=650, max_credit_score=850,
        allowed_states="ALL", geography_status="confirmed",
        verified=True,
        cash_flow_requirement="$100K revenue min, $200K preferred",
        min_dscr=None, min_annual_revenue=100000,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
    dict(
        name="Celtic Bank",
        contact_email="BSmith@celticbank.com",
        min_credit_score=680, max_credit_score=850,
        allowed_states="ALL", geography_status="confirmed",
        verified=False,
        cash_flow_requirement="DSCR 1.20x", min_dscr=1.20, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
    dict(
        # Contact email and geography both pending clarification. Inactive.
        name="KeyBank",
        contact_email=None,
        min_credit_score=680, max_credit_score=850,
        allowed_states=None, geography_status="needs_clarification",
        verified=False,
        cash_flow_requirement="DSCR 1.15x", min_dscr=1.15, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=False,
    ),
    dict(
        # Contact email and geography both pending clarification. Inactive.
        name="TD Bank",
        contact_email=None,
        min_credit_score=680, max_credit_score=850,
        allowed_states=None, geography_status="needs_clarification",
        verified=False,
        cash_flow_requirement="DSCR 1.15x", min_dscr=1.15, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=False,
    ),
    dict(
        # Minnesota only for now, per Karon.
        name="Scale Bank",
        contact_email="ann.franklin@scale.bank",
        min_credit_score=680, max_credit_score=850,
        allowed_states="MN", geography_status="provisional",
        verified=False,
        cash_flow_requirement="DSCR 1.25x", min_dscr=1.25, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
    dict(
        name="United Midwest",
        contact_email="loanservicing@umwsb.com",
        min_credit_score=680, max_credit_score=850,
        allowed_states="ALL", geography_status="confirmed",
        verified=False,
        cash_flow_requirement="DSCR 1.20x", min_dscr=1.20, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
    dict(
        name="South State Bank",
        contact_email="ddwarika@southstatebank.com",
        min_credit_score=680, max_credit_score=850,
        allowed_states="GA", geography_status="confirmed",
        verified=False,
        cash_flow_requirement="DSCR 1.25x", min_dscr=1.25, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
    dict(
        # The sheet only says "South East". This state list is an assumption
        # and needs confirming. Edit it with PATCH /admin/lenders/{id}.
        name="HTB",
        contact_email="brian.moon@htb.com",
        min_credit_score=680, max_credit_score=850,
        allowed_states="AL,FL,GA,KY,MS,NC,SC,TN,VA,WV", geography_status="provisional",
        verified=False,
        cash_flow_requirement="DSCR 1.25x", min_dscr=1.25, min_annual_revenue=None,
        years_in_business_required=2, pfs_required=True, active=True,
    ),
]


def seed_lenders():
    db = SessionLocal()
    try:
        for seed in SEED_LENDERS:
            lender = db.query(BankProfile).filter(BankProfile.name == seed["name"]).first()
            if lender is None:
                db.add(BankProfile(**seed))
                continue
            for field, value in seed.items():
                if field != "name" and value is not None and getattr(lender, field) is None:
                    setattr(lender, field, value)
        db.commit()
    finally:
        db.close()


def seed_bank_users():
    """
    Creates one login per active bank with a contact email, using the
    unique per-bank passwords stored in the BANK_PASSWORDS Railway
    variable (JSON of {email: password}). Banks with no entry get NO
    login. This is replaced by invitations and MFA in the next phase.
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


seed_lenders()
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
