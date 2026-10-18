import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from urllib.parse import quote

PORTAL_SECRET = os.environ.get("BANK_PORTAL_SECRET", "")
TOKEN_TTL_SECONDS = 60 * 60 * 8  # 8-hour session
MIN_PASSWORD_LENGTH = 12


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return f"{salt.hex()}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, derived_hex = stored_hash.split("$")
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(derived_hex)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return hmac.compare_digest(derived, expected)


def validate_password(password: str, email: str):
    """Raises ValueError with a user-friendly message if the password is too weak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in password.lower():
        raise ValueError("Password must not contain your email name.")


# ---------- signed tokens (access sessions and MFA challenges) ----------

def _sign(payload_b64: str) -> str:
    if not PORTAL_SECRET:
        raise RuntimeError("BANK_PORTAL_SECRET is not set")
    sig = hmac.new(PORTAL_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def create_token(bank_user_id: int, bank_profile_id: int, typ: str = "access", ttl: int = None) -> str:
    payload = {
        "bank_user_id": bank_user_id,
        "bank_profile_id": bank_profile_id,
        "typ": typ,
        "exp": int(time.time()) + (ttl or TOKEN_TTL_SECONDS),
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def verify_token(token: str, typ: str = "access"):
    try:
        payload_b64, signature = token.split(".")
    except ValueError:
        return None

    expected_sig = _sign(payload_b64)
    if not hmac.compare_digest(signature, expected_sig):
        return None

    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None

    if payload.get("typ") != typ:
        return None
    if payload.get("exp", 0) < time.time():
        return None

    return payload


# ---------- invitation tokens ----------

def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- MFA (TOTP, RFC 6238, standard library only) ----------

def generate_mfa_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret: str, code: str, last_step=None, window: int = 1):
    """
    Returns the matched time step on success, or None. A step at or
    before last_step is rejected, so a code can only be used once.
    """
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return None
    current = int(time.time() // 30)
    for step in range(current - window, current + window + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(_hotp(secret, step), code):
            return step
    return None


def otpauth_uri(secret: str, email: str, issuer: str = "Capital Goose") -> str:
    label = quote(f"{issuer}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
        "&algorithm=SHA1&digits=6&period=30"
    )
