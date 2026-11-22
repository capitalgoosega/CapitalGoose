"""
Public, no-login status page for lenders. Reached from the handoff email.

The link token is the credential. GET only SHOWS the page (email scanners
open links automatically, so GET must never change anything); a status
changes only when the lender presses a button, which POSTs back here.
"""
from datetime import datetime, timezone
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine import statuses as S
from app.engine.lender_links import REASON_CODES, allowed_actions, hash_link_token
from app.engine.referral_service import InvalidTransition, record_status
from app.models.bank_profile import BankProfile
from app.models.partner import LenderStatusLink, Referral
from app.services.audit_service import log_event

router = APIRouter()

_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow",
    "X-Frame-Options": "DENY",
}
_STYLE = (
    "body{font-family:sans-serif;max-width:560px;margin:48px auto;padding:0 16px;color:#0f172a}"
    "button{font-size:16px;padding:10px 16px;margin:4px 4px 4px 0;border:1px solid #0f766e;"
    "background:#0f766e;color:#fff;border-radius:8px;cursor:pointer}"
    "button.alt{background:#fff;color:#0f766e}select{font-size:16px;padding:8px;margin:8px 0}"
    ".muted{color:#475569}"
)


def _page(title, body_html, status_code=200):
    html = (
        f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
        f"<meta name='robots' content='noindex'><title>{escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><h2>{escape(title)}</h2>{body_html}</body></html>"
    )
    return HTMLResponse(html, status_code=status_code, headers=_HEADERS)


def _invalid():
    # One message for unknown, expired and revoked links, so the page reveals nothing.
    return _page("Link not available", "<p>This link is invalid or has expired. Please contact the Capital Goose team.</p>", 404)


def _load(db, token):
    link = db.query(LenderStatusLink).filter(LenderStatusLink.token_hash == hash_link_token(token)).first()
    if not link or link.revoked or link.expires_at < datetime.now(timezone.utc):
        return None, None
    referral = db.query(Referral).filter(Referral.id == link.referral_id).first()
    return (link, referral) if referral else (None, None)


def _form(token, referral):
    actions = allowed_actions(referral.status)
    if not actions:
        return "<p>No further updates can be recorded for this file.</p>"
    options = "".join(f"<option value='{k}'>{escape(v)}</option>" for k, v in REASON_CODES.items())
    buttons = "".join(
        f"<button type='submit' name='status' value='{s}' class='{'alt' if s == S.DECLINED else ''}'>{escape(label)}</button>"
        for s, label in actions
    )
    reason = (
        f"<p class='muted'>If declining, pick a reason:<br><select name='reason_code'>{options}</select></p>"
        if any(s == S.DECLINED for s, _ in actions) else ""
    )
    return f"<form method='post' action='/lender-status/{escape(token)}'>{reason}{buttons}</form>"


@router.get("/{token}", response_class=HTMLResponse, tags=["lender-status"])
def show(token: str, db: Session = Depends(get_db)):
    link, referral = _load(db, token)
    if not link:
        return _invalid()
    bank = db.query(BankProfile).filter(BankProfile.id == link.bank_profile_id).first()
    body = (
        f"<p class='muted'>Reference {escape(referral.public_id)}"
        f"{' &middot; ' + escape(referral.business_name) if referral.business_name else ''}<br>"
        f"Current status: <strong>{escape(referral.status.replace('_', ' '))}</strong>"
        f"{' &middot; ' + escape(bank.name) if bank else ''}</p>"
        f"<p>Update this file:</p>{_form(token, referral)}"
    )
    return _page("Capital Goose - file status", body)


@router.post("/{token}", response_class=HTMLResponse, tags=["lender-status"])
async def update(token: str, request: Request, db: Session = Depends(get_db)):
    link, referral = _load(db, token)
    if not link:
        return _invalid()
    # Form body parsed by hand so no multipart dependency is needed.
    form = parse_qs((await request.body()).decode("utf-8", "ignore"), keep_blank_values=True)
    status = (form.get("status") or [""])[0]
    reason = (form.get("reason_code") or [""])[0] or None

    if status not in {s for s, _ in allowed_actions(referral.status)}:
        return _page("Not recorded", f"<p>That update isn't available right now.</p>{_form(token, referral)}", 409)
    if status == S.DECLINED:
        if reason not in REASON_CODES:
            return _page("Reason needed", f"<p>Please choose a reason for declining.</p>{_form(token, referral)}", 422)
    else:
        reason = None

    bank = db.query(BankProfile).filter(BankProfile.id == link.bank_profile_id).first()
    try:
        record_status(db, referral, status, detail=f"reported by lender via link ({bank.name if bank else 'unknown'})",
                      source="lender", reason_code=reason)
    except InvalidTransition:
        return _page("Not recorded", "<p>That update isn't available right now.</p>", 409)

    link.use_count = (link.use_count or 0) + 1
    link.last_used_at = datetime.now(timezone.utc)
    if status in (S.FUNDED, S.DECLINED):
        link.revoked = True   # nothing further to report
    db.commit()
    log_event(db, f"[lender-link] referral {referral.public_id} -> {status} by {bank.name if bank else 'lender'}")
    return _page("Thank you", f"<p>Recorded: <strong>{escape(status.replace('_', ' '))}</strong>.</p>")
