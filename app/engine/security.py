"""
Small security helpers for the partner API: API keys, webhook signing and
public ids. Pure functions with no database or framework imports, so they
are easy to test.
"""
import hashlib
import hmac
import secrets
import time
from typing import Optional

KEY_MODES = ("sandbox", "live")


def generate_api_key(mode: str):
    """Returns (full_key, display_prefix, sha256_hash). The full key is shown once."""
    if mode not in KEY_MODES:
        raise ValueError(f"mode must be one of {KEY_MODES}")
    key = f"cg_{mode}_{secrets.token_urlsafe(32)}"
    return key, key[:12], hash_api_key(key)


def hash_api_key(key: str) -> str:
    # Keys are 256 bits of randomness, so a fast hash is appropriate here
    # (it is not a user-chosen password).
    return hashlib.sha256(key.encode()).hexdigest()


def generate_webhook_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(32)


def new_public_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


def sign_webhook(secret: str, body: bytes, timestamp: Optional[int] = None) -> str:
    """Header value: 't=<unix>,v1=<hex hmac-sha256 of "<t>.<body>">'."""
    ts = int(time.time()) if timestamp is None else int(timestamp)
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify_webhook_signature(secret: str, body: bytes, header: str,
                             tolerance_seconds: int = 300, now: Optional[int] = None) -> bool:
    """What a partner runs on their side. Included so we can test and document it."""
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        provided = parts["v1"]
    except (KeyError, ValueError):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - ts) > tolerance_seconds:
        return False
    expected = sign_webhook(secret, body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, provided)
