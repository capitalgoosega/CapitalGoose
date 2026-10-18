from sqlalchemy import Column, Integer, String, Boolean, Float
from app.db.session import Base

STATE_NAMES = {
    "AL": "ALABAMA", "AK": "ALASKA", "AZ": "ARIZONA", "AR": "ARKANSAS",
    "CA": "CALIFORNIA", "CO": "COLORADO", "CT": "CONNECTICUT", "DE": "DELAWARE",
    "DC": "DISTRICT OF COLUMBIA", "FL": "FLORIDA", "GA": "GEORGIA", "HI": "HAWAII",
    "ID": "IDAHO", "IL": "ILLINOIS", "IN": "INDIANA", "IA": "IOWA",
    "KS": "KANSAS", "KY": "KENTUCKY", "LA": "LOUISIANA", "ME": "MAINE",
    "MD": "MARYLAND", "MA": "MASSACHUSETTS", "MI": "MICHIGAN", "MN": "MINNESOTA",
    "MS": "MISSISSIPPI", "MO": "MISSOURI", "MT": "MONTANA", "NE": "NEBRASKA",
    "NV": "NEVADA", "NH": "NEW HAMPSHIRE", "NJ": "NEW JERSEY", "NM": "NEW MEXICO",
    "NY": "NEW YORK", "NC": "NORTH CAROLINA", "ND": "NORTH DAKOTA", "OH": "OHIO",
    "OK": "OKLAHOMA", "OR": "OREGON", "PA": "PENNSYLVANIA", "RI": "RHODE ISLAND",
    "SC": "SOUTH CAROLINA", "SD": "SOUTH DAKOTA", "TN": "TENNESSEE", "TX": "TEXAS",
    "UT": "UTAH", "VT": "VERMONT", "VA": "VIRGINIA", "WA": "WASHINGTON",
    "WV": "WEST VIRGINIA", "WI": "WISCONSIN", "WY": "WYOMING",
}
VALID_STATE_CODES = set(STATE_NAMES.keys())
_NAME_TO_CODE = {name: code for code, name in STATE_NAMES.items()}

GEOGRAPHY_STATUSES = {"confirmed", "provisional", "needs_clarification"}


def to_state_code(value):
    """Accepts 'GA' or 'Georgia' (any case) and returns 'GA', or None if unrecognized."""
    if not value:
        return None
    cleaned = str(value).strip().upper()
    if cleaned in VALID_STATE_CODES:
        return cleaned
    return _NAME_TO_CODE.get(cleaned)


def normalize_allowed_states(value):
    """
    Cleans up an allowed_states value. Returns None (unknown), "ALL"
    (nationwide), or a sorted comma-separated list of state codes.
    Raises ValueError on anything unrecognized.
    """
    if value is None:
        return None
    cleaned = str(value).strip().upper()
    if not cleaned:
        return None
    if cleaned == "ALL":
        return "ALL"
    codes = set()
    for part in cleaned.split(","):
        code = to_state_code(part)
        if not code:
            raise ValueError(f"Unrecognized state: {part.strip()!r}")
        codes.add(code)
    return ",".join(sorted(codes))


class BankProfile(Base):
    """
    A lending partner. Lender rules live here as data so they can be
    changed through the admin endpoints without redeploying.

    allowed_states: "ALL" = nationwide, "MN" or "GA,FL" = those states only,
    blank/NULL = unknown, which NEVER matches (fails closed).

    min_dscr, min_annual_revenue, years_in_business_required and
    pfs_required are stored but not enforced until the eligibility
    engine is built.
    """
    __tablename__ = "bank_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    contact_email = Column(String, nullable=True)

    min_credit_score = Column(Integer, nullable=False, default=0)
    max_credit_score = Column(Integer, nullable=False, default=850)

    allowed_states = Column(String, nullable=True)
    # confirmed | provisional | needs_clarification
    geography_status = Column(String, nullable=True, default="confirmed")

    verified = Column(Boolean, default=False)

    cash_flow_requirement = Column(String, nullable=True)
    min_dscr = Column(Float, nullable=True)
    min_annual_revenue = Column(Integer, nullable=True)
    years_in_business_required = Column(Integer, nullable=True, default=2)
    pfs_required = Column(Boolean, default=True)

    active = Column(Boolean, default=True)

    def accepts_state(self, applicant_state) -> bool:
        states = (self.allowed_states or "").strip().upper()
        if not states:
            return False  # geography unknown: never match
        if states == "ALL":
            return True
        code = to_state_code(applicant_state)
        if not code:
            return False  # applicant state missing or unrecognized
        return code in {s.strip() for s in states.split(",")}
