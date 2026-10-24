"""
Reads the JSON that Cognito Forms posts directly ("Post JSON Data to a
Website") for the Capital Goose Loan Application and turns it into an
IntakeRequest.

Cognito sends the whole entry, nested by form section, e.g.

    {
      "Id": "2-67",
      "Form": {"InternalName": "CapitalGooseLoanApplication", ...},
      "General": {"FirstName": ..., "DateOfBirth": "1999-12-26",
                  "BusinessAddress": {"Line1": ..., "City": ..., ...}, ...},
      "Finance": {"SelectALoanType": ..., "LoanAmountRequested": "10000", ...},
      "ConsentPrivacy": {"SignatureForConsentToPullCredit": {...},
                         "IAgreeToTheCapitolGoosePrivacyPolicy": true, ...},
      "Entry": {"Action": "Submit", "Number": 67, ...}
    }

The payload also contains the SSN, EIN, phone and document links. Nothing
in this module logs or returns those; only the fields the intake needs
are read.
"""

import re
from typing import Any, Optional

from app.schemas.intake import IntakeRequest

EXPECTED_FORM_INTERNAL_NAME = "CapitalGooseLoanApplication"


class CognitoPayloadError(ValueError):
    """The payload is not a usable loan application. The message is safe to log
    (it names fields, never their values)."""


def _section(payload: dict, name: str) -> dict:
    value = payload.get(name)
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required(value: Any, field: str) -> str:
    text = _text(value)
    if not text:
        raise CognitoPayloadError(f"missing_{field}")
    return text


def parse_loan_amount(value: Any) -> int:
    """Accepts 10000, "10000", "$10,000" or "10000.00"."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount = float(value)
    else:
        cleaned = re.sub(r"[,$\s]", "", _text(value))
        if not re.fullmatch(r"\d+(\.\d+)?", cleaned):
            raise CognitoPayloadError("invalid_loan_amount")
        amount = float(cleaned)
    if amount <= 0 or amount > 100_000_000:
        raise CognitoPayloadError("invalid_loan_amount")
    return int(round(amount))


def entry_id(payload: dict) -> Optional[str]:
    """Cognito's entry id, e.g. "2-67" (form 2, entry 67)."""
    value = _text(payload.get("Id"))
    return value or None


def has_credit_pull_consent(payload: dict) -> bool:
    consent = _section(payload, "ConsentPrivacy")
    signature = consent.get("SignatureForConsentToPullCredit")
    signed = isinstance(signature, dict) and bool(signature.get("Png") or signature.get("Svg"))
    agreed = consent.get("IAgreeToTheCapitolGoosePrivacyPolicy") is True
    return signed and agreed


def describe_shape(payload: Any, depth: int = 3) -> Any:
    """Field names and value TYPES only, for diagnosing a rejected payload.
    Never includes values, so it is safe to log even though the payload holds
    SSN/EIN."""
    if isinstance(payload, dict):
        if depth <= 0:
            return "dict"
        return {str(k): describe_shape(v, depth - 1) for k, v in payload.items()}
    if isinstance(payload, list):
        return f"list[{len(payload)}]"
    return type(payload).__name__


def parse_loan_application(payload: Any) -> IntakeRequest:
    if not isinstance(payload, dict):
        raise CognitoPayloadError("payload_not_object")

    form = _section(payload, "Form")
    form_name = _text(form.get("InternalName"))
    if form_name and form_name != EXPECTED_FORM_INTERNAL_NAME:
        raise CognitoPayloadError("unexpected_form")

    action = _text(_section(payload, "Entry").get("Action"))
    if action and action != "Submit":
        raise CognitoPayloadError("not_a_submission")

    if not entry_id(payload):
        raise CognitoPayloadError("missing_entry_id")

    if not has_credit_pull_consent(payload):
        raise CognitoPayloadError("missing_credit_pull_consent")

    general = _section(payload, "General")
    finance = _section(payload, "Finance")
    address = _section(general, "BusinessAddress")

    return IntakeRequest(
        first_name=_required(general.get("FirstName"), "first_name"),
        last_name=_required(general.get("LastName"), "last_name"),
        email=_required(general.get("EmailAddress"), "email"),
        loan_amount=parse_loan_amount(finance.get("LoanAmountRequested")),
        loan_type=_required(finance.get("SelectALoanType"), "loan_type"),
        dob=_required(general.get("DateOfBirth"), "date_of_birth"),
        address={
            "street": _required(address.get("Line1") or address.get("StreetAddress"), "street"),
            "city": _required(address.get("City"), "city"),
            "state": _required(address.get("State"), "state"),
            "zip": _required(address.get("PostalCode"), "zip"),
        },
    )
