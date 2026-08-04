from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.intake import IntakeRequest
from app.models.application import Application
from app.services.workflow_service import process_intake

router = APIRouter()

@router.post("/")
def submit_intake(data: IntakeRequest, db: Session = Depends(get_db)):
    try:
        status = process_intake(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    application = Application(
        name=f"{data.first_name} {data.last_name}",
        email=data.email,
        loan_amount=data.loan_amount,
        loan_type=data.loan_type,
        status=status
    )
    db.add(application)
    db.commit()
    db.refresh(application)
    return {
        "application_id": application.id,
        "status": application.status,
        "next_step": (
            "Complete collection package"
            if status == "pre_approved"
            else "Reapply when eligible"
        )
    }
