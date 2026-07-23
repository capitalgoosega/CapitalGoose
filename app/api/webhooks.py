import hashlib
import hmac
import logging
import os
import uuid
from fastapi import APIRouter, Request, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db
from app.models.application import Application
from app.services.workflow_service import process_intake, process_package
from app.schemas.intake import IntakeRequest

router = APIRouter()
logger = logging.getLogger("capitalgoose.webhook")
WEBHOOK_SECRET = os.environ["CAPITAL_GOOSE_WEBHOOK_KEY"]


@router.post("/cognito")
async def cognito_webhook(request: Request, db: Session = Depends(get_db)):

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
async def cognito_package_webhook(request: Request, db: Session = Depends(get_db)):

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

