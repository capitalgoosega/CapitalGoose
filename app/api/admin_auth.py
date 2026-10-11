import hmac
import os

from fastapi import Header, HTTPException


def require_admin(x_admin_key: str = Header(None)):
    """
    Guards internal-only endpoints. Requires an X-Admin-Key header that
    matches the ADMIN_API_KEY Railway variable. If the variable is not
    set, every request is rejected (fails closed).
    """
    expected = os.environ.get("ADMIN_API_KEY", "")
    if not expected or not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Admin access required")
