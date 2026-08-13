import mimetypes
import os
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

from app.models.access_code import DocumentAccessGrant, generate_access_code
from app.models.document_blob import DocumentBlob

ACCESS_GRANT_TTL_DAYS = int(os.environ.get("ACCESS_GRANT_TTL_DAYS", 7))

def ingest_document_from_url(db: Session, application_id, source_url, filename=None):
  response = requests.get(source_url, timeout=30)
  response.raise_for_status()
  safe_name = filename or source_url.split("/")[-1].split("?")[0] or "document"
  content_type = response.headers.get("Content-Type") or mimetypes.guess_type(safe_name)[0]
  blob = DocumentBlob(
  application_id=application_id,
  filename=safe_name,
  content_type=content_type,
  content=response.content,
  )
  db.add(blob)
  db.commit()
  db.refresh(blob)
  return blob.id

def ingest_application_documents(db: Session, application_id, document_urls: dict) -> list:
  return [
    ingest_document_from_url(db, application_id, url, filename=label)
    for label, url in document_urls.items()
  ]

def list_documents(db: Session, application_id):
  return db.query(DocumentBlob).filter(DocumentBlob.application_id == application_id).all()

def get_document(db: Session, doc_id: int):
  return db.query(DocumentBlob).filter(DocumentBlob.id == doc_id).first()

def create_access_grant(db: Session, application_id, recipient_email, recipient_label=None):
  grant = DocumentAccessGrant(
    application_id=application_id,
    code=generate_access_code(),
    recipient_email=recipient_email,
    recipient_label=recipient_label,
    expires_at=DocumentAccessGrant.default_expiry(ACCESS_GRANT_TTL_DAYS),
  )
  db.add(grant)
  db.commit()
  db.refresh(grant)
  return grant

def validate_and_load_grant(db: Session, code: str):
  grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
  if not grant or grant.revoked:
    return None
  if grant.expires_at < datetime.now(timezone.utc):
    return None
  grant.access_count += 1
  grant.last_accessed_at = datetime.now(timezone.utc)
  db.commit()
  return grant

def revoke_grant(db: Session, code: str) -> bool:
  grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
  if not grant:
    return False
  grant.revoked = True
  db.commit()
  return True
