import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.application_financials import ApplicationFinancials
from app.models.eligibility_result import LenderEligibilityResult

router = APIRouter()


@router.get("/{application_id}", tags=["admin-eligibility"])
def get_eligibility(application_id: int, db: Session = Depends(get_db)):
    fin = (
        db.query(ApplicationFinancials)
        .filter(ApplicationFinancials.application_id == application_id)
        .order_by(ApplicationFinancials.id.desc())
        .first()
    )
    rows = (
        db.query(LenderEligibilityResult)
        .filter(LenderEligibilityResult.application_id == application_id)
        .order_by(LenderEligibilityResult.lender_id)
        .all()
    )
    if not fin and not rows:
        raise HTTPException(status_code=404, detail="No eligibility data for that application")

    return {
        "application_id": application_id,
        "financials": None if not fin else {
            "years_in_business": fin.years_in_business,
            "annual_revenue": fin.annual_revenue,
            "annual_net_operating_income": fin.annual_net_operating_income,
            "annual_debt_payments": fin.annual_debt_payments,
            "dscr": fin.dscr,
        },
        "lenders": [
            {
                "lender": r.lender_name,
                "eligible": r.eligible,
                "checks": json.loads(r.details or "[]"),
            }
            for r in rows
        ],
    }
