from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_user import BankUser
from app.models.bank_profile import BankProfile
from app.services.auth_service import (
    hash_password,
    verify_password,
    validate_password,
    create_token,
    verify_token,
    hash_invite_token,
    generate_mfa_secret,
    verify_totp,
    otpauth_uri,
)
from app.services.crypto_service import encrypt_bytes, decrypt_bytes

router = APIRouter()

MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
_DUMMY_HASH = hash_password("not-a-real-password")  # keeps timing the same for unknown emails


def _now():
    return datetime.now(timezone.utc)


def _is_locked(user) -> bool:
    return bool(user.locked_until and user.locked_until > _now())


def _register_failure(db: Session, user):
    user.failed_attempts = (user.failed_attempts or 0) + 1
    if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
        user.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
        user.failed_attempts = 0
    db.commit()


def _register_success(db: Session, user):
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = _now()
    db.commit()


def _user_for_invite(db: Session, token: str):
    user = db.query(BankUser).filter(BankUser.invite_token_hash == hash_invite_token(token or "")).first()
    if (
        not user
        or user.status != "invited"
        or not user.invite_expires_at
        or user.invite_expires_at < _now()
    ):
        raise HTTPException(
            status_code=400,
            detail="This invitation link is invalid or has expired. Please contact Capital Goose for a new one.",
        )
    return user


# ---------- login (password, then authenticator code) ----------

class BankLoginRequest(BaseModel):
    email: EmailStr
    password: str


class BankMfaRequest(BaseModel):
    challenge_token: str
    code: str


@router.post("/login", tags=["bank-portal"])
def bank_login(payload: BankLoginRequest, db: Session = Depends(get_db)):
    user = db.query(BankUser).filter(BankUser.email == payload.email.lower()).first()

    if user and _is_locked(user):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")

    usable = bool(user and user.status == "active" and user.password_hash)
    password_ok = verify_password(payload.password, user.password_hash if usable else _DUMMY_HASH)

    if not usable or not password_ok:
        if usable:
            _register_failure(db, user)
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.mfa_enabled or not user.mfa_secret_enc:
        raise HTTPException(status_code=403, detail="Account setup is incomplete. Please use your activation link.")

    challenge = create_token(user.id, user.bank_profile_id, typ="mfa", ttl=300)
    return {"mfa_required": True, "challenge_token": challenge}


@router.post("/login/mfa", tags=["bank-portal"])
def bank_login_mfa(payload: BankMfaRequest, db: Session = Depends(get_db)):
    claims = verify_token(payload.challenge_token, typ="mfa")
    if not claims:
        raise HTTPException(status_code=401, detail="Your login session expired. Please start again.")

    user = db.query(BankUser).filter(BankUser.id == claims["bank_user_id"]).first()
    if not user or user.status != "active" or not user.mfa_enabled or not user.mfa_secret_enc:
        raise HTTPException(status_code=401, detail="Invalid login")

    if _is_locked(user):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")

    secret = decrypt_bytes(user.mfa_secret_enc.encode()).decode()
    step = verify_totp(secret, payload.code, user.mfa_last_step)
    if step is None:
        _register_failure(db, user)
        raise HTTPException(status_code=401, detail="Invalid code")

    user.mfa_last_step = step
    _register_success(db, user)

    bank = db.query(BankProfile).filter(BankProfile.id == user.bank_profile_id).first()
    token = create_token(user.id, user.bank_profile_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "bank_name": bank.name if bank else None,
    }


# ---------- account activation (from the invitation email) ----------

class ActivateStartRequest(BaseModel):
    token: str
    password: str


class ActivateConfirmRequest(BaseModel):
    token: str
    code: str


@router.post("/activate/start", tags=["bank-portal"])
def activate_start(payload: ActivateStartRequest, db: Session = Depends(get_db)):
    user = _user_for_invite(db, payload.token)

    try:
        validate_password(payload.password, user.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    secret = generate_mfa_secret()
    user.password_hash = hash_password(payload.password)
    user.mfa_secret_enc = encrypt_bytes(secret.encode()).decode()
    user.mfa_enabled = False
    db.commit()

    return {"email": user.email, "secret": secret, "otpauth_uri": otpauth_uri(secret, user.email)}


@router.post("/activate/confirm", tags=["bank-portal"])
def activate_confirm(payload: ActivateConfirmRequest, db: Session = Depends(get_db)):
    user = _user_for_invite(db, payload.token)

    if _is_locked(user):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
    if not user.password_hash or not user.mfa_secret_enc:
        raise HTTPException(status_code=400, detail="Please start the setup again.")

    secret = decrypt_bytes(user.mfa_secret_enc.encode()).decode()
    step = verify_totp(secret, payload.code, None)
    if step is None:
        _register_failure(db, user)
        raise HTTPException(status_code=401, detail="That code didn't match. Check the code in your authenticator app and try again.")

    user.mfa_enabled = True
    user.mfa_last_step = step
    user.status = "active"
    user.invite_token_hash = None
    user.invite_expires_at = None
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()

    return {"status": "active"}


# ---------- pages ----------

ACTIVATE_PAGE = """<!DOCTYPE html>
<html>
<head>
<title>Capital Goose - Activate Your Account</title>
<style>
body { font-family: Arial, sans-serif; max-width: 480px; margin: 60px auto; color: #222; }
input { width: 100%; padding: 8px; margin: 6px 0 14px; box-sizing: border-box; }
button { padding: 10px 16px; cursor: pointer; }
code { font-size: 16px; word-break: break-all; }
#error { color: #b00020; margin-top: 10px; }
</style>
</head>
<body>
<h2>Capital Goose — Activate Your Secure Account</h2>

<div id="step1">
  <p>Choose a password (at least 12 characters). Next you'll set up an authenticator app.</p>
  <label>Password</label>
  <input id="password" type="password" autocomplete="new-password" />
  <label>Confirm password</label>
  <input id="password2" type="password" autocomplete="new-password" />
  <button onclick="startSetup()">Continue</button>
</div>

<div id="step2" style="display:none;">
  <p>Add this account to an authenticator app (Google Authenticator, Microsoft Authenticator, Authy, 1Password, and others). Choose "enter a setup key" and type in:</p>
  <p><strong>Account:</strong> <span id="acct"></span></p>
  <p><strong>Setup key:</strong> <code id="secret"></code></p>
  <p><a id="otplink" href="#">On a phone? Tap here to open your authenticator app</a></p>
  <p>Then enter the 6-digit code the app shows:</p>
  <input id="code" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
  <button onclick="confirmSetup()">Activate account</button>
</div>

<div id="done" style="display:none;">
  <h3>Your account is active.</h3>
  <p>To view a collection package, open the secure link in your Capital Goose notification email and sign in with your email, password, and authenticator code.</p>
</div>

<div id="error"></div>

<script>
const token = new URLSearchParams(location.hash.replace(/^#/, '')).get('t') || '';

function setError(msg) { document.getElementById('error').textContent = msg || ''; }

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body)
  });
  const data = await res.json().catch(() => ({}));
  return {ok: res.ok, data: data};
}

function message(data, fallback) {
  return (data && typeof data.detail === 'string') ? data.detail : fallback;
}

async function startSetup() {
  setError('');
  const p1 = document.getElementById('password').value;
  const p2 = document.getElementById('password2').value;
  if (p1 !== p2) { setError('Passwords do not match.'); return; }
  const r = await post('/bank-portal/activate/start', {token: token, password: p1});
  if (!r.ok) { setError(message(r.data, 'Unable to continue. Please check your entries.')); return; }
  document.getElementById('acct').textContent = r.data.email;
  document.getElementById('secret').textContent = r.data.secret;
  document.getElementById('otplink').href = r.data.otpauth_uri;
  document.getElementById('step1').style.display = 'none';
  document.getElementById('step2').style.display = 'block';
}

async function confirmSetup() {
  setError('');
  const code = document.getElementById('code').value;
  const r = await post('/bank-portal/activate/confirm', {token: token, code: code});
  if (!r.ok) { setError(message(r.data, 'Unable to activate. Please try again.')); return; }
  document.getElementById('step2').style.display = 'none';
  document.getElementById('done').style.display = 'block';
}
</script>
</body>
</html>"""


ACCESS_PAGE = """<!DOCTYPE html>
<html>
<head>
<title>Capital Goose - Secure Bank Portal</title>
<style>
body { font-family: Arial, sans-serif; max-width: 480px; margin: 60px auto; color: #222; }
input { width: 100%; padding: 8px; margin: 6px 0 14px; box-sizing: border-box; }
button { padding: 10px 16px; cursor: pointer; }
#error { color: #b00020; margin-top: 10px; }
#docs li { margin: 8px 0; }
</style>
</head>
<body>
<h2>Capital Goose — Secure Document Portal</h2>

<div id="login-section">
  <label>Email</label>
  <input id="email" type="email" autocomplete="username" />
  <label>Password</label>
  <input id="password" type="password" autocomplete="current-password" />
  <label>Access Code</label>
  <input id="code" type="text" />
  <button onclick="login()">Continue</button>
</div>

<div id="mfa-section" style="display:none;">
  <p>Enter the 6-digit code from your authenticator app.</p>
  <input id="mfa" inputmode="numeric" maxlength="6" autocomplete="one-time-code" />
  <button onclick="verifyMfa()">View Documents</button>
</div>

<div id="docs-section" style="display:none;">
  <h3 id="bank-name"></h3>
  <ul id="docs"></ul>
</div>

<div id="error"></div>

<script>
let token = null;
let challenge = null;
let currentCode = null;

document.getElementById('code').value = new URLSearchParams(location.search).get('code') || '';

function setError(msg) { document.getElementById('error').textContent = msg || ''; }

function message(data, fallback) {
  return (data && typeof data.detail === 'string') ? data.detail : fallback;
}

async function login() {
  setError('');
  currentCode = document.getElementById('code').value;
  const res = await fetch('/bank-portal/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      email: document.getElementById('email').value,
      password: document.getElementById('password').value
    })
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { setError(message(data, 'Invalid email or password.')); return; }
  challenge = data.challenge_token;
  document.getElementById('login-section').style.display = 'none';
  document.getElementById('mfa-section').style.display = 'block';
}

async function verifyMfa() {
  setError('');
  const res = await fetch('/bank-portal/login/mfa', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({challenge_token: challenge, code: document.getElementById('mfa').value})
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { setError(message(data, 'Invalid code.')); return; }
  token = data.access_token;
  document.getElementById('bank-name').textContent = data.bank_name || '';
  await loadDocuments();
}

async function loadDocuments() {
  const res = await fetch('/vault/' + encodeURIComponent(currentCode) + '/documents', {
    headers: {'Authorization': 'Bearer ' + token}
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    setError(message(body, 'Unable to load documents.'));
    return;
  }
  const data = await res.json();
  const list = document.getElementById('docs');
  list.innerHTML = '';
  data.documents.forEach(function (doc) {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = 'Download: ' + doc.filename;
    btn.onclick = function () { downloadDoc(doc.id, doc.filename); };
    li.appendChild(btn);
    list.appendChild(li);
  });
  document.getElementById('mfa-section').style.display = 'none';
  document.getElementById('docs-section').style.display = 'block';
}

async function downloadDoc(docId, filename) {
  const res = await fetch('/vault/' + encodeURIComponent(currentCode) + '/download/' + docId, {
    headers: {'Authorization': 'Bearer ' + token}
  });
  if (!res.ok) { alert('Unable to download document.'); return; }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
</script>
</body>
</html>"""


@router.get("/activate", response_class=HTMLResponse, tags=["bank-portal"])
def activate_page():
    return ACTIVATE_PAGE


@router.get("/access", response_class=HTMLResponse, tags=["bank-portal"])
def access_page():
    return ACCESS_PAGE
