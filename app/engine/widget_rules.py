"""Validation for hosted-widget sessions. Pure functions."""
import re

SESSION_TTL_MINUTES = 30

_ORIGIN = re.compile(r"^https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$")
_LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d{1,5})?$")

# Fields a partner may prefill. Anything else is rejected, so the session
# can't be used to smuggle arbitrary content into the page.
PREFILL_FIELDS = {
    "first_name", "last_name", "email",
    "legal_name", "state",
    "years_in_business", "annual_revenue",
    "loan_amount", "loan_type",
}


def valid_origin(origin: str, allow_local: bool = False) -> bool:
    """An exact origin (scheme + host [+ port]) with no path, for postMessage and frame-ancestors."""
    if not origin or len(origin) > 200:
        return False
    return bool(_ORIGIN.match(origin) or (allow_local and _LOCAL_ORIGIN.match(origin)))


def clean_prefill(prefill):
    """Returns (cleaned dict of short strings, error or None)."""
    if not isinstance(prefill, dict):
        return {}, "prefill must be an object"
    unknown = sorted(set(prefill) - PREFILL_FIELDS)
    if unknown:
        return {}, f"unknown prefill fields: {', '.join(unknown)}"
    out = {}
    for k, v in prefill.items():
        if isinstance(v, bool) or not isinstance(v, (str, int, float)):
            return {}, f"prefill.{k} must be text or a number"
        text = str(v).strip()
        if len(text) > 120:
            return {}, f"prefill.{k} is too long"
        out[k] = text
    return out, None
