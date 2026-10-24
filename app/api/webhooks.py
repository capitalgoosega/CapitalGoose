import hashlib
import hmac
import logging
import os
import uuid
from fastapi import BackgroundTasks
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db
from app.models.application import Application
from app.services.workflow_service import process_intake, process_package
from app.schemas.intake import IntakeRequest
from app.services.cognito_payload import (
    CognitoPayloadError,
    entry_id as cognito_entry_id,
    parse_loan_application,
)

router = APIRouter()
logger = logging.getLogger("capitalgoose.webhook")
WEBHOOK_SECRET = os.environ["CAPITAL_GOOSE_WEBHOOK_KEY"]

# Separate secret for Cognito's direct "Post JSON" webhook. Cognito can't send
# custom headers, so it travels in the URL (?key=...). Read at request time so
# a missing variable disables only this endpoint instead of crashing startup.
COGNITO_TOKEN_ENV = "COGNITO_WEBHOOK_TOKEN"


def _require_webhook_key(received_key: str):
    if not received_key or not hmac.compare_digest(received_key, WEBHOOK_SECRET):
        logger.warning("webhook auth failed")
        raise HTTPException(status_code=401, detail="invalid_webhook_key")


@router.post("/cognito")
async def cognito_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_capital_goose_webhook_key: str = Header(None),
):
    _require_webhook_key(x_capital_goose_webhook_key)

    raw = await request.json()

    try:
        intake_data = IntakeRequest(
            first_name=raw["Entry.FirstName"],
            last_name=raw["Entry.LastName"],
            email=raw["Entry.EmailAddress"],
            loan_amount=int(raw["Entry.LoanAmount"]),
            loan_type=raw["Entry.LoanType"],
            dob=raw["Entry.DateOfBirth"],
            address={
                "street": raw["Entry.Street"],
                "city": raw["Entry.City"],
                "state": raw["Entry.State"],
                "zip": raw["Entry.ZipCode"],
            }
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"Missing field from Cognito: {e}")

    status = process_intake(db, intake_data)

    app_record = Application(
        name=f"{intake_data.first_name} {intake_data.last_name}",
        email=intake_data.email,
        loan_amount=intake_data.loan_amount,
        loan_type=intake_data.loan_type,
        status=status
    )

    db.add(app_record)
    db.commit()

    return {"received": True, "status": status}


@router.post("/cognito-package")
async def cognito_package_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_capital_goose_webhook_key: str = Header(None),
):
    _require_webhook_key(x_capital_goose_webhook_key)

    raw = await request.json()

    email = raw.get("EmailAddress") or raw.get("Entry.EmailAddress")
    if not email:
        raise HTTPException(status_code=400, detail="Missing email field")

    # look up their existing application by email
    application = (
        db.query(Application)
        .filter(Application.email == email)
        .order_by(Application.id.desc())
        .first()
    )

    if not application:
        raise HTTPException(status_code=404, detail="No application found for this email")

    if application.status != "pre_approved":
        raise HTTPException(status_code=400, detail="Application is not in pre_approved status")

    process_package(db, application, raw)
    db.commit()

    return {"received": True, "status": "submitted"}


@router.post("/zapier-application")
async def zapier_application_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_capital_goose_webhook_key: str = Header(None),
):
    request_id = str(uuid.uuid4())

    received_key = x_capital_goose_webhook_key or ""
    logger.warning(
        "zapier webhook key check request_id=%s received_len=%d expected_len=%d received_last4=%s expected_last4=%s",
        request_id, len(received_key), len(WEBHOOK_SECRET), received_key[-4:], WEBHOOK_SECRET[-4:]
    )
    if not x_capital_goose_webhook_key or not hmac.compare_digest(
        x_capital_goose_webhook_key, WEBHOOK_SECRET
    ):
        logger.warning("zapier webhook auth failed request_id=%s", request_id)
        raise HTTPException(status_code=401, detail="invalid_webhook_key")

    raw = await request.json()
    entry_id = raw.get("Entry.Id") or raw.get("EntryId") or raw.get("Entry.EntryId")

    try:
        intake_data = IntakeRequest(
            first_name=raw["Entry.FirstName"],
            last_name=raw["Entry.LastName"],
            email=raw["Entry.EmailAddress"],
            loan_amount=int(raw["Entry.LoanAmount"]),
            loan_type=raw["Entry.LoanType"],
            dob=raw["Entry.DateOfBirth"],
            address={
                "street": raw["Entry.Street"],
                "city": raw["Entry.City"],
                "state": raw["Entry.State"],
                "zip": raw["Entry.ZipCode"],
            }
        )
    except (KeyError, ValueError) as e:
        logger.info("zapier webhook invalid payload request_id=%s missing=%s", request_id, str(e))
        raise HTTPException(status_code=400, detail="invalid_request_data")

    if entry_id:
        existing = db.query(Application).filter(Application.source_entry_id == entry_id).first()
        if existing:
            logger.info("zapier webhook duplicate request_id=%s entry_id=%s", request_id, entry_id)
            raise HTTPException(status_code=409, detail="duplicate_application_request")

    try:
        status = process_intake(db, intake_data)
    except Exception as e:
        logger.error("zapier webhook processing failed request_id=%s error_type=%s", request_id, type(e).__name__)
        raise HTTPException(status_code=500, detail="internal_processing_failure")

    app_record = Application(
        source_entry_id=entry_id,
        name=f"{intake_data.first_name} {intake_data.last_name}",
        email=intake_data.email,
        loan_amount=intake_data.loan_amount,
        loan_type=intake_data.loan_type,
        status=status
    )
    db.add(app_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.info("zapier webhook duplicate on commit request_id=%s entry_id=%s", request_id, entry_id)
        raise HTTPException(status_code=409, detail="duplicate_application_request")

    logger.info("zapier webhook completed request_id=%s application_id=%s status=%s", request_id, app_record.id, status)

    return {"status": "success", "request_id": request_id, "application_id": app_record.id, "decision": status}


@router.post("/cognito-application")
async def cognito_application_webhook(
    request: Request,
    db: Session = Depends(get_db),
    key: str = "",
):
    """
    Receives the Capital Goose Loan Application directly from Cognito Forms
    (Build > Settings > Post JSON Data to a Website > Submit URL), replacing the
    Zapier hop so applicant data is no longer stored in Zapier's history.

    Submit URL to configure in Cognito:
        https://<railway-host>/webhooks/cognito-application?key=<COGNITO_WEBHOOK_TOKEN>

    The payload contains the full entry (including SSN). Never log it.
    """
    request_id = str(uuid.uuid4())

    expected = os.environ.get(COGNITO_TOKEN_ENV, "")
    if not expected:
        logger.error("cognito webhook disabled: %s not set request_id=%s", COGNITO_TOKEN_ENV, request_id)
        raise HTTPException(status_code=503, detail="webhook_not_configured")
    if not key or not hmac.compare_digest(key, expected):
        logger.warning("cognito webhook auth failed request_id=%s", request_id)
        raise HTTPException(status_code=401, detail="invalid_webhook_key")

    try:
        raw = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_json")

    try:
        intake_data = parse_loan_application(raw)
    except CognitoPayloadError as e:
        logger.info("cognito webhook rejected request_id=%s reason=%s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError:
        logger.info("cognito webhook rejected request_id=%s reason=invalid_fields", request_id)
        raise HTTPException(status_code=400, detail="invalid_request_data")

    entry_id = cognito_entry_id(raw)

    # Idempotency: Cognito retries failed posts, and the same entry must never run
    # the intake (emails now, a real credit pull later) twice. Claim the entry id
    # with the unique source_entry_id column BEFORE doing any work, so two
    # simultaneous deliveries can't both get through. Duplicates get a 200 so
    # Cognito stops retrying.
    app_record = Application(
        source_entry_id=entry_id,
        name=f"{intake_data.first_name} {intake_data.last_name}",
        email=intake_data.email,
        loan_amount=intake_data.loan_amount,
        loan_type=intake_data.loan_type,
        status="processing",
    )
    db.add(app_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Application).filter(Application.source_entry_id == entry_id).first()
        logger.info("cognito webhook duplicate request_id=%s entry_id=%s", request_id, entry_id)
        return {"status": "duplicate", "request_id": request_id, "application_id": existing.id if existing else None}

    def _release_claim():
        # Processing failed before anything was sent: drop the claim so a retry can run.
        db.rollback()
        db.query(Application).filter(Application.id == app_record.id).delete()
        db.commit()

    try:
        status = process_intake(db, intake_data)
    except ValueError:
        _release_claim()
        logger.info("cognito webhook invalid date of birth request_id=%s entry_id=%s", request_id, entry_id)
        raise HTTPException(status_code=400, detail="invalid_date_of_birth")
    except Exception as e:
        _release_claim()
        logger.error("cognito webhook processing failed request_id=%s error_type=%s", request_id, type(e).__name__)
        raise HTTPException(status_code=500, detail="internal_processing_failure")

    app_record.status = status
    db.commit()

    logger.info("cognito webhook completed request_id=%s application_id=%s status=%s", request_id, app_record.id, status)
    return {"status": "success", "request_id": request_id, "application_id": app_record.id, "decision": status}
