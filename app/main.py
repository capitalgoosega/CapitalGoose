from fastapi import FastAPI

from app.api.routes import router

from app.db.session import Base, engine, SessionLocal
from app.models.bank_profile import BankProfile


Base.metadata.create_all(bind=engine)


def seed_bank_profiles():
    """
    Seeds BankProfile from the Banking Partner Requirements mapping
    table (Karon, CTO). Replaces any existing rows (including earlier
    placeholder test banks) on every startup so this stays in sync
    with the code below.

    NOTE: this is a code-based seed, not a true no-code-editable
    config — see the note on BankProfile about that gap.

    KeyBank and TD Bank are seeded inactive (active=False) because no
    contact email has been provided for them yet. Flip active=True
    and set contact_email once available.

    Scale Bank is seeded as "nationwide" per the sheet's Geo column,
    though the sheet's own notes flag this as unconfirmed
    (MN-centered, out-of-state appetite unclear) — revisit once
    confirmed with the partner.
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
                active=False,  # no email yet — inactive until provided
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
                active=False,  # no email yet — inactive until provided
            ),
            BankProfile(
                name="Scale Bank",
                contact_email="ann.franklin@scale.bank",
                min_credit_score=680,
                max_credit_score=850,
                geographic_scope="nationwide",  # per sheet column — notes flag this as unconfirmed
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


seed_bank_profiles()


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
