from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from app.db.session import Base


def _now():
    return datetime.now(timezone.utc)


class Partner(Base):
    """A host app, CPA portal or chamber that calls the engine with an API key."""
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    # sandbox = simulated credit data allowed; live = real applicants, needs a real credit provider
    mode = Column(String, nullable=False, default="sandbox")
    api_key_prefix = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False, unique=True, index=True)
    active = Column(Boolean, nullable=False, default=True)
    webhook_url = Column(String, nullable=True)
    webhook_secret_enc = Column(String, nullable=True)  # Fernet-encrypted
    revenue_share_pct = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    revoked_at = Column(DateTime(timezone=True), nullable=True)


class Referral(Base):
    """One applicant routed through the engine for one partner."""
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("partner_id", "idempotency_key", name="uq_referral_idem"),)

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String, nullable=False, unique=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, unique=True)
    external_ref = Column(String, nullable=True, index=True)
    idempotency_key = Column(String, nullable=True)

    status = Column(String, nullable=False, default="received", index=True)
    business_name = Column(String, nullable=True)
    business_state = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    lender_name = Column(String, nullable=True)
    prequal_json = Column(Text, nullable=True)  # {matched, reasons, blockers}

    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    funded_at = Column(DateTime(timezone=True), nullable=True)
    declined_at = Column(DateTime(timezone=True), nullable=True)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)


class Consent(Base):
    """
    Written consent captured by the partner before any credit pull (FCRA
    permissible purpose). Never updated or deleted.
    """
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True, index=True)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=False, index=True)
    partner_id = Column(Integer, nullable=False)
    signer_name = Column(String, nullable=False)
    consent_version = Column(String, nullable=False)   # which consent wording the applicant saw
    permissible_purpose = Column(String, nullable=False, default="credit_prequalification")
    captured_at = Column(DateTime(timezone=True), nullable=False)   # when the partner says it was signed
    received_at = Column(DateTime(timezone=True), default=_now)     # when we got it
    signer_ip = Column(String, nullable=True)
    partner_ip = Column(String, nullable=True)


class StatusEvent(Base):
    """Append-only history of a referral's status. Feeds the timeline and webhooks."""
    __tablename__ = "referral_status_events"

    id = Column(Integer, primary_key=True, index=True)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    source = Column(String, nullable=False, default="engine")  # engine | admin | lender
    detail = Column(String, nullable=True)  # internal note; never sent to partners
    reason_code = Column(String, nullable=True)  # lender decline reason (internal outcome data)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String, nullable=False, unique=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False, index=True)
    referral_id = Column(Integer, nullable=True)
    event_type = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)  # pending | delivered | failed
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), default=_now, index=True)
    last_status_code = Column(Integer, nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    delivered_at = Column(DateTime(timezone=True), nullable=True)


class LenderStatusLink(Base):
    """
    A no-login link a lender uses to report milestones for ONE referral.
    The token is a capability: only its hash is stored, and it is revoked
    once the referral reaches funded or declined.
    """
    __tablename__ = "lender_status_links"

    id = Column(Integer, primary_key=True, index=True)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=False, index=True)
    bank_profile_id = Column(Integer, ForeignKey("bank_profiles.id"), nullable=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked = Column(Boolean, nullable=False, default=False)
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class WidgetSession(Base):
    """
    A short-lived, single-use session the partner's SERVER mints so an
    applicant's browser can use the hosted form without ever seeing an API key.
    Only the token's hash is stored.
    """
    __tablename__ = "widget_sessions"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    external_ref = Column(String, nullable=True)
    allowed_origin = Column(String, nullable=True)   # partner site that may frame the widget
    prefill_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=True)  # set once submitted
