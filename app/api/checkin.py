"""
Public one-tap check-in page for borrowers. Reached from the check-in email.

GET only SHOWS the page (email scanners open links); a POST records the answer.
"""
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.engine.followups import BORROWER_ANSWERS
from app.engine.lender_links import hash_link_token
from app.engine.followup_service import CHECKIN_LINK_DAYS, _aware
from app.models.partner import BorrowerCheckin, FollowUp, Referral
from app.services.audit_service import log_event

router = APIRouter()

_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow", "X-Frame-Options": "DENY"}
_STYLE = ("body{font-family:sans-serif;max-width:520px;margin:48px auto;padding:0 16px;color:#0f172a}"
          "button{display:block;width:100%;font-size:16px;padding:12px;margin:8px 0;border:1px solid #0f766e;"
          "background:#fff;color:#0f766e;border-radius:8px;cursor:pointer}.muted{color:#475569}")


def _page(title, body, status=200):
    html = (f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            f"<meta name='robots' content='noindex'><title>{escape(title)}</title><style>{_STYLE}</style></head>"
            f"<body><h2>{escape(title)}</h2>{body}</body></html>")
    return HTMLResponse(html, status_code=status, headers=_HEADERS)


def _invalid():
    return _page("Link not available", "<p>This link is invalid or has expired.</p>", 404)


def _load(db, token):
    fu = db.query(FollowUp).filter(FollowUp.token_hash == hash_link_token(token), FollowUp.kind.like("borrower_%")).first()
    if not fu or _aware(fu.sent_at) + timedelta(days=CHECKIN_LINK_DAYS) < datetime.now(timezone.utc):
        return None, None
    ref = db.query(Referral).filter(Referral.id == fu.referral_id).first()
    return (fu, ref) if ref else (None, None)


@router.get("/{token}", response_class=HTMLResponse, tags=["checkin"])
def show(token: str, db: Session = Depends(get_db)):
    fu, ref = _load(db, token)
    if not fu:
        return _invalid()
    buttons = "".join(f"<button type='submit' name='answer' value='{k}'>{escape(v)}</button>" for k, v in BORROWER_ANSWERS.items())
    return _page("How is your loan going?",
                 f"<p class='muted'>Your file was sent to {escape(ref.lender_name or 'our lending partner')}. Tap the answer that fits best.</p>"
                 f"<form method='post' action='/checkin/{escape(token)}'>{buttons}</form>")


@router.post("/{token}", response_class=HTMLResponse, tags=["checkin"])
async def record(token: str, request: Request, db: Session = Depends(get_db)):
    fu, ref = _load(db, token)
    if not fu:
        return _invalid()
    form = parse_qs((await request.body()).decode("utf-8", "ignore"), keep_blank_values=True)
    answer = (form.get("answer") or [""])[0]
    if answer not in BORROWER_ANSWERS:
        return _page("Not recorded", "<p>Please choose one of the options.</p>", 422)
    db.add(BorrowerCheckin(referral_id=ref.id, followup_id=fu.id, answer=answer))
    db.commit()
    log_event(db, f"[checkin] referral {ref.public_id} answered {answer}")
    return _page("Thank you", "<p>Your answer was recorded. We appreciate it.</p>")
