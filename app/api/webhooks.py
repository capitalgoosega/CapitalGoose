from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.application import Application
from app.services.workflow_service import process_intake
from app.schemas.intake import IntakeRequest

router = APIRouter()

@router.post("/cognito")
async def cognito_webhook(request: Request, db: Session = Depends(get_db)):

    raw = await request.json()
    print("RAW PAYLOAD:", raw)

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
        print("RAW PAYLOAD DUMP:", raw)
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
