import base64
import hashlib
import hmac
import json
import os
import time

PORTAL_SECRET = os.environ.get("BANK_PORTAL_SECRET", "")
TOKEN_TTL_SECONDS = 60 * 60 * 8  # 8-hour session


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


def _sign(payload_b64: str) -> str:
    if not PORTAL_SECRET:
        raise RuntimeError("BANK_PORTAL_SECRET is not set")
    sig = hmac.new(PORTAL_SECRET.encode(), payload_b64.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode().rstrip("=")


def create_token(bank_user_id: int, bank_profile_id: int) -> str:
    payload = {
        "bank_user_id": bank_user_id,
        "bank_profile_id": bank_profile_id,
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = _sign(payload_b64)
    return f"{payload_b64}.{signature}"


def verify_token(token: str):
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

    if payload.get("exp", 0) < time.time():
        return None

    return payload
