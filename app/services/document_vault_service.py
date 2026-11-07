import mimetypes
import os
from datetime import datetime, timezone

import requests
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.access_code import DocumentAccessGrant, generate_access_code
from app.models.access_log import DocumentAccessLog
from app.models.bank_profile import BankProfile
from app.models.bank_user import BankUser
from app.models.document_blob import DocumentBlob
from app.services.crypto_service import encrypt_bytes, decrypt_bytes

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
        content=encrypt_bytes(response.content),
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


def get_decrypted_content(doc: DocumentBlob) -> bytes:
    """Call this wherever a document's raw bytes are actually served (e.g. the download route)."""
    return decrypt_bytes(doc.content)


def create_access_grant(db: Session, application_id, recipient_email, recipient_label=None, bank_profile_id=None):
    grant = DocumentAccessGrant(
        application_id=application_id,
        code=generate_access_code(),
        recipient_email=recipient_email,
        recipient_label=recipient_label,
        bank_profile_id=bank_profile_id,
        expires_at=DocumentAccessGrant.default_expiry(ACCESS_GRANT_TTL_DAYS),
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def check_grant(db: Session, code: str):
    """
    Looks up a code WITHOUT counting it as an access.
    Returns (grant, problem): problem is None when the code is usable,
    otherwise "unknown_code", "revoked" or "expired".
    """
    grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
    if not grant:
        return None, "unknown_code"
    if grant.revoked:
        return grant, "revoked"
    if grant.expires_at < datetime.now(timezone.utc):
        return grant, "expired"
    return grant, None


def record_grant_access(db: Session, grant):
    """Counts a real, authorized access to a grant."""
    grant.access_count = (grant.access_count or 0) + 1
    grant.last_accessed_at = datetime.now(timezone.utc)
    db.commit()


def validate_and_load_grant(db: Session, code: str):
    grant, problem = check_grant(db, code)
    if problem:
        return None
    record_grant_access(db, grant)
    return grant


def revoke_grant(db: Session, code: str) -> bool:
    grant = db.query(DocumentAccessGrant).filter(DocumentAccessGrant.code == code).first()
    if not grant:
        return False
    grant.revoked = True
    db.commit()
    return True


def log_document_access(db: Session, grant, bank: dict, action: str, doc=None):
    """Records one successful access. `bank` is the verified login token payload."""
    user = db.query(BankUser).filter(BankUser.id == bank.get("bank_user_id")).first()
    profile = db.query(BankProfile).filter(BankProfile.id == bank.get("bank_profile_id")).first()

    db.add(DocumentAccessLog(
        application_id=grant.application_id,
        grant_id=grant.id,
        bank_name=profile.name if profile else None,
        bank_user_email=user.email if user else None,
        action=action,
        document_id=doc.id if doc else None,
        filename=doc.filename if doc else None,
        outcome="success",
    ))
    db.commit()


def log_blocked_access(db: Session, bank: dict, reason: str, action: str, code: str = "", grant=None, doc_id=None):
    """
    Records a refused attempt by a signed-in bank user. Only the last four
    characters of the attempted code are kept. If logging itself fails, the
    request is still refused: this never turns a refusal into an error.
    """
    try:
        user = db.query(BankUser).filter(BankUser.id == bank.get("bank_user_id")).first()
        profile = db.query(BankProfile).filter(BankProfile.id == bank.get("bank_profile_id")).first()

        db.add(DocumentAccessLog(
            application_id=grant.application_id if grant else None,
            grant_id=grant.id if grant else None,
            bank_name=profile.name if profile else None,
            bank_user_email=user.email if user else None,
            action=action,
            document_id=doc_id,
            outcome="blocked",
            reason=reason,
            code_hint=("..." + code[-4:]) if code else None,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"AUDIT LOG ERROR (blocked access not recorded): {type(e).__name__}")


def list_access_log(db: Session, application_id=None, outcome=None, limit: int = 200):
    query = db.query(DocumentAccessLog)
    if application_id is not None:
        query = query.filter(DocumentAccessLog.application_id == application_id)
    if outcome == "blocked":
        query = query.filter(DocumentAccessLog.outcome == "blocked")
    elif outcome == "success":
        query = query.filter(or_(DocumentAccessLog.outcome == "success", DocumentAccessLog.outcome.is_(None)))
    return query.order_by(DocumentAccessLog.accessed_at.desc()).limit(limit).all()
