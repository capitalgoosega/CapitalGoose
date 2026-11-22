"""
Documents in, lender handoff out.

Handoff = give the matched lender (1) portal access to the encrypted documents
through the existing access-code vault and (2) a private no-login link to
report milestones. Nothing containing applicant data goes in the email.
"""
import os
from datetime import datetime, timedelta, timezone

from app.engine import statuses as S
from app.engine.documents import (
    MAX_FILES_PER_REFERRAL, required_doc_types, missing_doc_types, safe_filename,
)
from app.engine.lender_links import LINK_TTL_DAYS, new_link_token
from app.engine.referral_service import record_status
from app.models.access_code import DocumentAccessGrant
from app.models.application import Application
from app.models.bank_profile import BankProfile
from app.models.document_blob import DocumentBlob
from app.models.partner import LenderStatusLink, Partner
from app.services.audit_service import log_event
from app.services.crypto_service import encrypt_bytes
from app.services.document_vault_service import create_access_grant
from app.services.email_service import send_lender_handoff_email


class HandoffError(Exception):
    """A reason the handoff can't proceed; the message is safe to show the caller."""


def _base_url():
    return os.environ.get("APP_BASE_URL", "https://capitalgoose-production.up.railway.app").rstrip("/")


def store_document(db, referral, doc_type, filename, data, content_type):
    count = db.query(DocumentBlob).filter(DocumentBlob.application_id == referral.application_id).count()
    if count >= MAX_FILES_PER_REFERRAL:
        raise HandoffError(f"A referral can hold at most {MAX_FILES_PER_REFERRAL} documents")
    blob = DocumentBlob(
        application_id=referral.application_id,
        filename=safe_filename(filename),
        content_type=content_type,
        doc_type=doc_type,
        content=encrypt_bytes(data),   # encrypted at rest, same as the Cognito-era documents
    )
    db.add(blob)
    db.commit()
    db.refresh(blob)
    log_event(db, f"[api] document {blob.id} ({doc_type}) uploaded for referral {referral.public_id}")
    return blob


def document_summary(db, referral):
    lender = db.query(BankProfile).filter(BankProfile.name == referral.lender_name).first() if referral.lender_name else None
    required = required_doc_types(bool(lender.pfs_required) if lender else True)
    blobs = (
        db.query(DocumentBlob)
        .filter(DocumentBlob.application_id == referral.application_id)
        .order_by(DocumentBlob.id)
        .all()
    )
    return {
        "required": required,
        "missing": missing_doc_types([b.doc_type for b in blobs if b.doc_type], required),
        "documents": [
            {"id": b.id, "doc_type": b.doc_type, "filename": b.filename,
             "content_type": b.content_type, "uploaded_at": b.created_at}
            for b in blobs
        ],
    }


def send_handoff(db, referral, lender):
    """
    Creates a fresh access grant + status link (revoking any earlier ones for
    this referral) and emails the lender. Used for the first handoff and resends.
    """
    partner = db.query(Partner).filter(Partner.id == referral.partner_id).first()
    sandbox = partner is None or partner.mode != "live"
    test_inbox = os.environ.get("TEST_RECIPIENT_EMAIL")

    recipient = lender.contact_email
    suppress_email = False
    if sandbox:
        # Sandbox referrals use simulated data and must NEVER reach a real lender.
        recipient = test_inbox
        suppress_email = not test_inbox
        log_event(db, f"[handoff] sandbox referral {referral.public_id}: " + (
            "redirected to test inbox" if test_inbox else "lender email suppressed"))
    elif os.environ.get("TEST_MODE", "").lower() == "true" and test_inbox:
        recipient = test_inbox
        log_event(db, f"TEST MODE: handoff for {lender.name} redirected to test inbox")
    if not recipient and not suppress_email:
        raise HandoffError(f"No contact email is configured for {lender.name}")
    recipient = recipient or "sandbox-suppressed@invalid"

    for old in db.query(DocumentAccessGrant).filter(
        DocumentAccessGrant.application_id == referral.application_id,
        DocumentAccessGrant.bank_profile_id == lender.id,
        DocumentAccessGrant.revoked == False,  # noqa: E712
    ).all():
        old.revoked = True
    for old in db.query(LenderStatusLink).filter(
        LenderStatusLink.referral_id == referral.id, LenderStatusLink.revoked == False,  # noqa: E712
    ).all():
        old.revoked = True
    db.commit()

    grant = create_access_grant(db, referral.application_id, recipient, lender.name, bank_profile_id=lender.id)
    token, token_hash = new_link_token()
    db.add(LenderStatusLink(
        referral_id=referral.id, bank_profile_id=lender.id, token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=LINK_TTL_DAYS),
    ))
    db.commit()

    if not suppress_email:
        send_lender_handoff_email(recipient, lender.name, grant.code, f"{_base_url()}/lender-status/{token}")
    log_event(db, f"[handoff] referral {referral.public_id} sent to {lender.name}")


def handoff(db, referral):
    """Partner says the file is complete: verify, hand off, mark submitted."""
    if referral.status != S.PREQUALIFIED:
        raise HandoffError(f"Referral is '{referral.status}'; only prequalified referrals can be submitted")
    lender = db.query(BankProfile).filter(BankProfile.name == referral.lender_name).first()
    if not lender or not lender.active:
        raise HandoffError("The matched lender is no longer available; contact Capital Goose")

    summary = document_summary(db, referral)
    if summary["missing"]:
        raise HandoffError("Missing required documents: " + ", ".join(summary["missing"]))

    send_handoff(db, referral, lender)
    app_row = db.query(Application).filter(Application.id == referral.application_id).first()
    if app_row:
        app_row.lender = lender.name
    record_status(db, referral, S.SUBMITTED, detail=f"handed off to {lender.name}")
    return referral
