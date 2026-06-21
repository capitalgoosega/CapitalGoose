from pydantic import BaseModel


class Address(BaseModel):
    street: str
    city: str
    state: str
    zip: str


class IntakeRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    loan_amount: int
    loan_type: str
    ssn: str
    dob: str        # format: "YYYY-MM-DD"
    address: Address
