"""
The headless engine's core: take a partner's referral, capture consent,
prequalify, route to a single best-fit lender, and track status.
"""
import json
from datetime import datetime, timezone

from app.engine import statuses as S
from app.engine.credit_provider import PullRequest, get_provider
from app.engine.loan_range import likely_range
from app.engine.reasons import match_reasons, no_match_blockers
from app.engine.security import new_public_id
from app.engine.webhook_service import enqueue_event
from app.models.application import Application
from app.models.eligibility_result import LenderEligibilityResult
from app.models.partner import Consent, Partner, Referral, StatusEvent
from app.services.audit_service import log_event
from app.services.credit_service import verify_age
from app.services.eligibility_service import evaluate_lenders, extract_financials, save_financials


class InvalidTransition(Exception):
    pass


class EngineUnavailable(Exception):
    """Raised when we must not proceed (e.g. live partner but no real credit provider)."""


def _now():
    return datetime.now(timezone.utc)


def record_status(db, referral, new_status, detail=None, source="engine", force=False, reason_code=None):
    """Moves a referral to a new status, writes the history row, queues the webhook."""
    if not force and not S.can_transition(referral.status, new_status):
        raise InvalidTransition(f"cannot move from '{referral.status}' to '{new_status}'")

    referral.status = new_status
    now = _now()
    if new_status == S.SUBMITTED and referral.submitted_at is None:
        referral.submitted_at = now
    elif new_status == S.FUNDED:
        referral.funded_at = now
    elif new_status == S.DECLINED:
        referral.declined_at = now
    elif new_status == S.WITHDRAWN:
        referral.withdrawn_at = now

    db.add(StatusEvent(referral_id=referral.id, status=new_status, source=source, detail=detail, reason_code=reason_code))

    mapped = S.APPLICATION_STATUS.get(new_status)
    if mapped:
        app_row = db.query(Application).filter(Application.id == referral.application_id).first()
        if app_row:
            app_row.status = mapped
    db.commit()

    partner = db.query(Partner).filter(Partner.id == referral.partner_id).first()
    enqueue_event(db, partner, referral, f"referral.{new_status}")
    return referral


def sync_application_status(db, application_id, new_status, detail=None):
    """
    Called by the older Cognito-era flow (process_package) so a referral's
    status follows the application. Does nothing when the application has no
    referral, and never raises: the existing flow must not break because of this.
    """
    try:
        referral = db.query(Referral).filter(Referral.application_id == application_id).first()
        if referral and S.can_transition(referral.status, new_status):
            record_status(db, referral, new_status, detail=detail, source="engine")
    except Exception:
        db.rollback()


def create_referral(db, partner, payload, idempotency_key=None, partner_ip=None):
    """
    Returns (referral, created). Raises ValueError for bad input (e.g. a date
    of birth we can't parse) and EngineUnavailable / ProviderNotConfigured
    when the engine must not proceed.
    """
    if idempotency_key:
        existing = (
            db.query(Referral)
            .filter(Referral.partner_id == partner.id, Referral.idempotency_key == idempotency_key)
            .first()
        )
        if existing:
            return existing, False

    provider = get_provider()
    if partner.mode == "live" and provider.simulated:
        raise EngineUnavailable(
            "No real credit provider is configured yet, so live referrals can't be processed. "
            "Use a sandbox key until the credit provider is connected."
        )

    is_adult = verify_age(payload.applicant.dob)   # raises ValueError on a bad date

    applicant, business, loan = payload.applicant, payload.business, payload.loan
    public_id = new_public_id("ref")

    application = Application(
        source_entry_id=f"api:{public_id}",
        name=f"{applicant.first_name} {applicant.last_name}",
        email=applicant.email,
        loan_amount=loan.amount,
        loan_type=loan.type,
        status="received",
    )
    db.add(application)
    db.flush()

    referral = Referral(
        public_id=public_id,
        partner_id=partner.id,
        application_id=application.id,
        external_ref=payload.external_ref,
        idempotency_key=idempotency_key,
        status=S.RECEIVED,
        business_name=business.legal_name,
        business_state=business.state,
        industry=business.industry,
    )
    db.add(referral)
    db.flush()

    db.add(Consent(
        referral_id=referral.id,
        partner_id=partner.id,
        signer_name=payload.consent.signer_name,
        consent_version=payload.consent.consent_version,
        captured_at=payload.consent.captured_at,
        signer_ip=payload.consent.ip_address,
        partner_ip=partner_ip,
    ))
    db.add(StatusEvent(referral_id=referral.id, status=S.RECEIVED, source="engine"))
    db.commit()
    log_event(db, f"[api] referral {public_id} received from partner {partner.id}; consent {payload.consent.consent_version} recorded")

    # Age gate happens BEFORE any credit pull.
    if not is_adult:
        referral.prequal_json = json.dumps({
            "matched": False, "reasons": [],
            "blockers": [{"criterion": "age", "message": "Applicant must be 18 or older"}],
        })
        record_status(db, referral, S.DECLINED, detail="failed age verification")
        return referral, True

    # Credit pull (consent is already stored above).
    try:
        pull = provider.pull(db, application.id, PullRequest(
            first_name=applicant.first_name, last_name=applicant.last_name,
            dob=applicant.dob, address=applicant.address.model_dump(),
        ))
    except Exception:
        # Free the idempotency key so the partner's retry starts a fresh referral
        # instead of replaying this stuck one.
        referral.idempotency_key = None
        db.add(StatusEvent(referral_id=referral.id, status=S.RECEIVED, source="engine", detail="credit pull failed"))
        db.commit()
        log_event(db, f"[credit_pull] FAILED referral {public_id} provider={provider.name}")
        raise
    log_event(db, f"[credit_pull] referral {public_id} provider={provider.name} partner={partner.id}")

    application.credit_score = pull.credit_score
    db.commit()

    financials = extract_financials({
        "YearsInBusiness": business.years_in_business,
        "AnnualRevenue": business.annual_revenue,
        "AnnualNetOperatingIncome": business.annual_net_operating_income,
        "AnnualDebtPayments": business.annual_debt_payments,
    })
    save_financials(db, application.id, financials)

    # The Personal Financial Statement is collected at handoff, so don't let its
    # absence rule everyone out at prequalification.
    eligible = evaluate_lenders(db, application.id, pull.credit_score, business.state, financials, True, loan_amount=loan.amount)

    results = (
        db.query(LenderEligibilityResult)
        .filter(LenderEligibilityResult.application_id == application.id)
        .all()
    )
    checks_by_lender = {r.lender_name: json.loads(r.details or "[]") for r in results}

    if eligible:
        best = eligible[0]
        application.lender = best.name
        referral.lender_name = best.name
        referral.prequal_json = json.dumps({
            "matched": True,
            "reasons": match_reasons(checks_by_lender.get(best.name, [])),
            "blockers": [],
            "likely_range": likely_range(best.min_loan_amount, best.max_loan_amount),
        })
        record_status(db, referral, S.PREQUALIFIED, detail=f"matched {best.name}")
    else:
        referral.prequal_json = json.dumps({
            "matched": False,
            "reasons": [],
            "blockers": no_match_blockers(list(checks_by_lender.values())),
        })
        record_status(db, referral, S.NO_MATCH, detail="no eligible lender")

    return referral, True


def serialize_referral(db, referral, include_internal=False):
    prequal = json.loads(referral.prequal_json) if referral.prequal_json else {}
    events = (
        db.query(StatusEvent)
        .filter(StatusEvent.referral_id == referral.id)
        .order_by(StatusEvent.id)
        .all()
    )
    out = {
        "referral_id": referral.public_id,
        "external_ref": referral.external_ref,
        "status": referral.status,
        "created_at": referral.created_at,
        "updated_at": referral.updated_at,
        "prequalification": {
            "matched": bool(prequal.get("matched")),
            "lender": referral.lender_name if prequal.get("matched") else None,
            # Null until the lender's loan-size limits are configured.
            "likely_range": prequal.get("likely_range") if prequal.get("matched") else None,
            "reasons": prequal.get("reasons", []),
            "blockers": prequal.get("blockers", []),
        },
        "timeline": [{"status": e.status, "at": e.created_at} for e in events if not (e.detail == "credit pull failed")],
    }
    if include_internal:
        out["partner_id"] = referral.partner_id
        out["application_id"] = referral.application_id
        out["business_state"] = referral.business_state
        out["timeline"] = [
            {"status": e.status, "at": e.created_at, "source": e.source, "detail": e.detail, "reason_code": e.reason_code}
            for e in events
        ]
    return out
