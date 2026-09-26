from sqlalchemy import Column, Integer, String, Boolean
from app.db.session import Base

# Geographic scopes map to the actual set of eligible states.
# "nationwide" means no restriction. Update this mapping if a bank's
# footprint changes or gets confirmed more precisely (e.g. once TD's
# exact 15-state + DC list, or Scale's real out-of-state appetite, is
# confirmed with the partner).
GEOGRAPHIC_SCOPES = {
    "nationwide": None,  # None = no restriction, always eligible
    "georgia": {"GA"},
    "south_east": {"AL", "FL", "GA", "KY", "MS", "NC", "SC", "TN", "VA", "WV"},
    "tri_state": set(),  # TODO: exact states unconfirmed — currently blocks all matches until defined
}


class BankProfile(Base):
    """
    A queryable lending partner profile, sourced from the Banking
    Partner Requirements mapping table (Karon, CTO).

    NOTE on configurability: this table is currently seeded via code
    (see main.py) rather than edited through an admin tool, so adding
    or updating a bank still requires a code change + redeploy. This
    does not yet meet the "no code change needed" requirement from the
    requirements doc — flag to Karon as a phase-2 item if that matters
    before more partners are added.
    """
    __tablename__ = "bank_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    contact_email = Column(String, nullable=True)

    min_credit_score = Column(Integer, nullable=False, default=0)
    max_credit_score = Column(Integer, nullable=False, default=850)

    # One of the keys in GEOGRAPHIC_SCOPES above.
    geographic_scope = Column(String, nullable=False, default="nationwide")

    # True only for banks verified against a published credit box (per
    # the mapping table notes). False = market-standard assumption,
    # not yet confirmed with the partner directly.
    verified = Column(Boolean, default=False)

    # Reference-only fields below: displayed for underwriting context,
    # NOT enforced automatically in matching. Cognito Forms doesn't
    # currently collect structured revenue/cash-flow/years-in-business
    # data, so these can't be auto-checked yet.
    cash_flow_requirement = Column(String, nullable=True)
    years_in_business_required = Column(Integer, nullable=True, default=2)
    pfs_required = Column(Boolean, default=True)

    active = Column(Boolean, default=True)

    def accepts_state(self, applicant_state: str) -> bool:
        allowed = GEOGRAPHIC_SCOPES.get(self.geographic_scope)
        if allowed is None:
            return True  # nationwide
        if not applicant_state:
            return False  # unknown state — don't risk matching a regional bank
        return applicant_state.strip().upper() in allowed
