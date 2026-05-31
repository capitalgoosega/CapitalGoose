from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.package import PackageRequest
from app.models.application import Application
from app.services.workflow_service import process_package

router = APIRouter()

@router.post("/")
def submit_package(data: PackageRequest, db: Session = Depends(get_db)):

    application = (
        db.query(Application)
        .filter(Application.id == data.application_id)
        .first()
    )

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    process_package(db, application, data)

    db.commit()
    db.refresh(application)

    return {
        "application_id": application.id,
        "status": application.status,
        "lender": application.lender,
        "message": "Loan package submitted to bank systems"
    }