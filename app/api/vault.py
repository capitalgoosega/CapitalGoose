from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import document_vault_service as vault

router = APIRouter()


class CreateAccessGrantRequest(BaseModel):
  application_id: int
  recipient_email: EmailStr
  recipient_label: Optional[str] = None

@router.post("/access-grants", tags=["vault"])
def create_access_grant(payload: CreateAccessGrantRequest, db: Session = Depends(get_db)):
  grant = vault.create_access_grant(
    db,
    application_id=payload.application_id,
    recipient_email=payload.recipient_email,
    recipient_label=payload.recipient_label,
  )
  return {
  "code": grant.code,
  "expires_at": grant.expires_at,
  "access_url_path": f"/vault/{grant.code}",
  }


@router.get("/{code}", response_class=HTMLResponse, tags=["vault"])
def view_documents(code: str, db: Session = Depends(get_db)):
  grant = vault.validate_and_load_grant(db, code)
  if not grant:
    raise HTTPException(status_code=404, detail="This link is invalid, revoked, or has expired.")
  keys = vault.list_document_keys(grant.application_id)
  if not keys:
    rows = "<p>No documents are available for this application yet.</p>"
  else:
    rows = "<ul>" + "".join(
          f'<li><a href="{vault.generate_presigned_download_url(k)}">{k.split("/")[-1]}</a></li>'
      for k in keys
    ) + "</ul>"
  html = (
  "<html><head><title>Capital Goose - Secure Documents</title></head>"
  '<body style="font-family: sans-serif; max-width: 600px; margin: 60px auto;">'
  "<h2>Application Documents</h2>"
  '<p style="color:#666;">Download links expire in 15 minutes. Refresh this page for new links.</p>'
  f"{rows}"
  "</body></html>"
  )
  return html
