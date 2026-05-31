from pydantic import BaseModel


class IntakeRequest(BaseModel):
    name: str
    email: str
    loan_amount: int
    loan_type: str
    ssn: str