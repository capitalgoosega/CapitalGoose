from pydantic import BaseModel

class PackageRequest(BaseModel):
    application_id: int
    loan_type: str
