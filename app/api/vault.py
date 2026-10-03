from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from app.services import document_vault_service as vault
from app.services.auth_service import verify_token
from app.db.session import get_db

router = APIRouter()


class CreateAccessGrantRequest(BaseModel):
    application_id: int
    recipient_email: EmailStr
    recipient_label: Optional[str] = None


def get_authenticated_bank(authorization: str = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization.split(" ", 1)[1]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session — please log in again")

    return payload


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
def view_documents(code: str, db: Session = Depends(get_db), bank=Depends(get_authenticated_bank)):
    grant = vault.validate_and_load_grant(db, code)
    if not grant:
        raise HTTPException(status_code=404, detail="This link is invalid, revoked, or has expired.")

    if grant.bank_profile_id != bank["bank_profile_id"]:
        raise HTTPException(status_code=403, detail="This access code is not assigned to your institution.")

    docs = vault.list_documents(db, grant.application_id)
    if not docs:
        rows = "<p>No documents are available for this application yet.</p>"
    else:
        rows = "<ul>" + "".join(
            f'<li><a href="/vault/{code}/download/{d.id}">{d.filename}</a></li>'
            for d in docs
        ) + "</ul>"

    html = (
        "<html><head><title>Capitol Goose - Secure Documents</title></head>"
        '<body style="font-family: sans-serif; max-width: 600px; margin: 60px auto;">'
        "<h2>Application Documents</h2>"
        + rows +
        "</body></html>"
    )
    return html


@router.get("/{code}/download/{doc_id}", tags=["vault"])
def download_document(code: str, doc_id: int, db: Session = Depends(get_db), bank=Depends(get_authenticated_bank)):
    grant = vault.validate_and_load_grant(db, code)
    if not grant:
        raise HTTPException(status_code=404, detail="This link is invalid, revoked, or has expired.")

    if grant.bank_profile_id != bank["bank_profile_id"]:
        raise HTTPException(status_code=403, detail="This access code is not assigned to your institution.")

    doc = vault.get_document(db, doc_id)
    if not doc or doc.application_id != grant.application_id:
        raise HTTPException(status_code=404, detail="Document not found.")

    return Response(
        content=vault.get_decrypted_content(doc),
        media_type=doc.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.filename}"'},
    )
