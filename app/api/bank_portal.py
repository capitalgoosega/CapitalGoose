from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.bank_user import BankUser
from app.models.bank_profile import BankProfile
from app.services.auth_service import verify_password, create_token

router = APIRouter()


class BankLoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", tags=["bank-portal"])
def bank_login(payload: BankLoginRequest, db: Session = Depends(get_db)):
    user = db.query(BankUser).filter(BankUser.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    bank = db.query(BankProfile).filter(BankProfile.id == user.bank_profile_id).first()
    token = create_token(user.id, user.bank_profile_id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "bank_name": bank.name if bank else None,
    }


@router.get("/access", response_class=HTMLResponse, tags=["bank-portal"])
def bank_portal_access_page(code: str = ""):
    return f"""<!DOCTYPE html>
<html>
<head>
<title>Capital Goose - Secure Bank Portal</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 480px; margin: 60px auto; color: #222; }}
input {{ width: 100%; padding: 8px; margin: 6px 0 14px; box-sizing: border-box; }}
button {{ padding: 10px 16px; cursor: pointer; }}
#error {{ color: #b00020; margin-top: 10px; }}
#docs li {{ margin: 8px 0; }}
</style>
</head>
<body>
<h2>Capital Goose — Secure Document Portal</h2>

<div id="login-section">
  <label>Email</label>
  <input id="email" type="email" />
  <label>Password</label>
  <input id="password" type="password" />
  <label>Access Code</label>
  <input id="code" type="text" value="{code}" />
  <button onclick="login()">View Documents</button>
  <div id="error"></div>
</div>

<div id="docs-section" style="display:none;">
  <h3 id="bank-name"></h3>
  <ul id="docs"></ul>
</div>

<script>
let token = null;
let currentCode = null;

async function login() {{
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  currentCode = document.getElementById('code').value;
  document.getElementById('error').textContent = '';

  const res = await fetch('/bank-portal/login', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{email, password}})
  }});

  if (!res.ok) {{
    document.getElementById('error').textContent = 'Invalid email or password.';
    return;
  }}

  const data = await res.json();
  token = data.access_token;
  document.getElementById('bank-name').textContent = data.bank_name || '';

  await loadDocuments();
}}

async function loadDocuments() {{
  const res = await fetch('/vault/' + currentCode + '/documents', {{
    headers: {{'Authorization': 'Bearer ' + token}}
  }});

  if (!res.ok) {{
    const body = await res.json().catch(() => ({{}}));
    document.getElementById('error').textContent = body.detail || 'Unable to load documents.';
    return;
  }}

  const data = await res.json();
  const list = document.getElementById('docs');
  list.innerHTML = '';
  data.documents.forEach(doc => {{
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.textContent = 'Download: ' + doc.filename;
    btn.onclick = () => downloadDoc(doc.id, doc.filename);
    li.appendChild(btn);
    list.appendChild(li);
  }});

  document.getElementById('login-section').style.display = 'none';
  document.getElementById('docs-section').style.display = 'block';
}}

async function downloadDoc(docId, filename) {{
  const res = await fetch('/vault/' + currentCode + '/download/' + docId, {{
    headers: {{'Authorization': 'Bearer ' + token}}
  }});
  if (!res.ok) {{
    alert('Unable to download document.');
    return;
  }}
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}}
</script>
</body>
</html>"""
