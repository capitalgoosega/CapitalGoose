from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.application import Application
from app.services.workflow_service import process_intake, process_package
from app.schemas.intake import IntakeRequest

router = APIRouter()


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
