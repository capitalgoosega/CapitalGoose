import hashlib

from app.engine import statuses as S
from app.engine.metrics import accuracy_summary
from app.engine.ratelimit import SlidingWindowLimiter
from app.engine.reasons import match_reasons, no_match_blockers
from app.engine.security import (
    generate_api_key, hash_api_key, sign_webhook, verify_webhook_signature, generate_webhook_secret,
)
from app.engine.urlsafety import is_safe_webhook_url


def test_api_key_hash_roundtrip_and_modes():
    key, prefix, key_hash = generate_api_key("sandbox")
    assert key.startswith("cg_sandbox_") and key.startswith(prefix)
    assert key_hash == hash_api_key(key) == hashlib.sha256(key.encode()).hexdigest()
    assert key not in key_hash
    live, *_ = generate_api_key("live")
    assert live.startswith("cg_live_")


def test_webhook_signature_valid_tampered_and_stale():
    secret, body = generate_webhook_secret(), b'{"a":1}'
    header = sign_webhook(secret, body, timestamp=1_000)
    assert verify_webhook_signature(secret, body, header, now=1_100)
    assert not verify_webhook_signature(secret, b'{"a":2}', header, now=1_100)
    assert not verify_webhook_signature("whsec_other", body, header, now=1_100)
    assert not verify_webhook_signature(secret, body, header, now=1_000 + 301)
    assert not verify_webhook_signature(secret, body, "garbage", now=1_100)


def test_status_transitions():
    ok = S.can_transition
    assert ok(S.RECEIVED, S.PREQUALIFIED) and ok(S.RECEIVED, S.NO_MATCH)
    assert ok(S.PREQUALIFIED, S.SUBMITTED)
    assert ok(S.SUBMITTED, S.APPROVED)          # may skip lender_received
    assert ok(S.CLOSING, S.FUNDED)
    assert not ok(S.APPROVED, S.SUBMITTED)      # no going backwards
    assert ok(S.PREQUALIFIED, S.FUNDED)         # forward jumps along the path are allowed
    assert ok(S.APPROVED, S.DECLINED) and ok(S.SUBMITTED, S.WITHDRAWN)
    for terminal in (S.FUNDED, S.DECLINED, S.WITHDRAWN, S.NO_MATCH):
        assert not ok(terminal, S.APPROVED)
    assert not ok(S.PREQUALIFIED, S.NO_MATCH)   # no_match only straight from received
    assert not ok("bogus", S.APPROVED) and not ok(S.RECEIVED, "bogus")


def _c(criterion, status):
    return {"criterion": criterion, "status": status, "detail": ""}


def test_match_reasons_never_leak_numbers():
    reasons = match_reasons([_c("credit_score", "pass"), _c("geography", "pass"), _c("dscr", "fail")])
    assert len(reasons) == 2 and not any(ch.isdigit() for r in reasons for ch in r)


def test_no_match_blockers_only_what_every_lender_failed():
    lender_a = [_c("credit_score", "fail"), _c("geography", "pass")]
    lender_b = [_c("credit_score", "fail"), _c("geography", "fail")]
    blockers = no_match_blockers([lender_a, lender_b])
    assert [b["criterion"] for b in blockers] == ["credit_score"]


def test_no_match_combination_and_no_lenders():
    a = [_c("credit_score", "pass"), _c("geography", "fail")]
    b = [_c("credit_score", "fail"), _c("geography", "pass")]
    assert no_match_blockers([a, b])[0]["criterion"] == "combination"
    assert no_match_blockers([])[0]["criterion"] == "no_lenders"


def test_accuracy_summary():
    s = accuracy_summary(submitted=10, funded=4, declined=2, withdrawn=1)
    assert s["lending_accuracy"] == 0.4 and s["pending"] == 3
    assert s["funded_of_decided"] == 4 / 6 and s["sample_is_small"] and s["note"]
    empty = accuracy_summary(0, 0, 0)
    assert empty["lending_accuracy"] is None and empty["funded_of_decided"] is None
    assert not accuracy_summary(60, 30, 10)["sample_is_small"]


def _resolver(ip):
    return lambda host, port: [(2, 1, 6, "", (ip, port))]


def test_webhook_url_safety():
    pub = _resolver("93.184.216.34")
    assert is_safe_webhook_url("https://partner.example.com/hook", resolver=pub)[0]
    assert not is_safe_webhook_url("http://partner.example.com/hook", resolver=pub)[0]
    for ip in ("127.0.0.1", "10.0.0.5", "169.254.169.254", "192.168.1.1"):
        assert not is_safe_webhook_url("https://x.example.com", resolver=_resolver(ip))[0], ip
    assert not is_safe_webhook_url("https://user:pw@x.example.com", resolver=pub)[0]
    assert not is_safe_webhook_url("https://x.example.com", resolver=_resolver("fe80::1%eth0"))[0]
    assert is_safe_webhook_url("http://localhost:9000/h", allow_insecure=True, resolver=_resolver("127.0.0.1"))[0]


def test_rate_limiter_window():
    t = [0.0]
    lim = SlidingWindowLimiter(2, 10, clock=lambda: t[0])
    assert lim.allow("k") and lim.allow("k") and not lim.allow("k")
    assert lim.allow("other")
    t[0] = 10.0
    assert lim.allow("k")


# ---- documents + lender links -------------------------------------------------
from app.engine.documents import (  # noqa: E402
    required_doc_types, missing_doc_types, sniff_content_type, safe_filename,
)
from app.engine.lender_links import allowed_actions, hash_link_token, new_link_token  # noqa: E402


def test_required_docs_and_missing():
    assert "personal_financial_statement" in required_doc_types(True)
    assert "personal_financial_statement" not in required_doc_types(False)
    req = required_doc_types(True)
    assert missing_doc_types(["bank_statement", "tax_return"], req) == ["government_id", "personal_financial_statement"]
    assert missing_doc_types(req, req) == []


def test_sniff_by_magic_bytes_not_claims():
    assert sniff_content_type(b"%PDF-1.7 ...") == "application/pdf"
    assert sniff_content_type(b"\x89PNG\r\n\x1a\nxx") == "image/png"
    assert sniff_content_type(b"\xff\xd8\xffxx") == "image/jpeg"
    assert sniff_content_type(b"MZ\x90\x00 an exe") is None
    assert sniff_content_type(b"<html><script>") is None


def test_safe_filename():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("C:\\Users\\x\\Statement Jan.pdf") == "Statement Jan.pdf"
    assert safe_filename("<script>.pdf") == "_script_.pdf"
    assert safe_filename("") == "document" and len(safe_filename("a" * 500)) == 100


def test_lender_link_tokens_and_actions():
    token, h = new_link_token()
    assert h == hash_link_token(token) and token not in h and len(token) >= 40
    assert new_link_token()[0] != token
    assert [s for s, _ in allowed_actions(S.SUBMITTED)] == [
        S.LENDER_RECEIVED, S.APPROVED, S.CLOSING, S.FUNDED, S.DECLINED]
    assert [s for s, _ in allowed_actions(S.CLOSING)] == [S.FUNDED, S.DECLINED]
    assert allowed_actions(S.FUNDED) == [] and allowed_actions(S.DECLINED) == []
    assert allowed_actions(S.PREQUALIFIED) != [] and S.SUBMITTED not in [s for s, _ in allowed_actions(S.PREQUALIFIED)]


# ---- loan range + widget rules -------------------------------------------------
from app.engine.loan_range import check_loan_amount, likely_range  # noqa: E402
from app.engine.widget_rules import clean_prefill, valid_origin  # noqa: E402


def test_loan_range_checks():
    assert check_loan_amount(None, None, 100_000) is None            # no limits configured: not enforced
    assert check_loan_amount(50_000, 500_000, 250_000)[0] == "pass"
    assert check_loan_amount(50_000, 500_000, 10_000)[0] == "fail"
    assert check_loan_amount(50_000, 500_000, 900_000)[0] == "fail"
    assert check_loan_amount(50_000, None, 60_000)[0] == "pass"      # open-ended
    assert check_loan_amount(50_000, 500_000, None)[0] == "unknown"
    assert likely_range(None, None) is None
    assert likely_range(50_000, 500_000) == {"min": 50_000, "max": 500_000}


def test_widget_origin_validation():
    assert valid_origin("https://app.partner.com")
    assert valid_origin("https://app.partner.com:8443")
    for bad in ("http://app.partner.com", "https://app.partner.com/path", "https://", "*",
                "https://a.com; script-src *", "javascript:alert(1)", ""):
        assert not valid_origin(bad), bad
    assert not valid_origin("http://localhost:3000")
    assert valid_origin("http://localhost:3000", allow_local=True)


def test_widget_prefill_whitelist():
    ok, err = clean_prefill({"first_name": " Pat ", "loan_amount": 250000})
    assert err is None and ok == {"first_name": "Pat", "loan_amount": "250000"}
    assert clean_prefill({"ssn": "123"})[1]                       # unknown field rejected
    assert clean_prefill({"email": ["x"]})[1]                     # wrong type rejected
    assert clean_prefill({"email": "x" * 500})[1]                 # too long rejected
    assert clean_prefill("nope")[1]


# ---- credit bands, upload check, follow-ups ----------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

from app.engine.credit_bands import BANDS, band_to_score  # noqa: E402
from app.engine.documents import check_upload  # noqa: E402
from app.engine.followups import due_followups  # noqa: E402


def test_credit_bands_are_conservative_lower_bounds():
    assert band_to_score("720_plus") == 720 and band_to_score("580_649") == 580
    assert band_to_score("below_580") < 580
    assert band_to_score("bogus") is None and band_to_score(None) is None
    assert sorted(BANDS.values()) == list(BANDS.values())


def test_check_upload():
    assert check_upload(b"%PDF-1.7 x")[0] == "application/pdf"
    assert check_upload(b"")[1] == 422
    assert check_upload(b"MZ binary")[1] == 415
    assert check_upload(b"%PDF-" + b"0" * (15 * 1024 * 1024))[1] == 413


def test_followups_schedule():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d = lambda days: t0 + timedelta(days=days)   # noqa: E731
    assert due_followups(d(3), t0, S.SUBMITTED, []) == []
    assert due_followups(d(7), t0, S.SUBMITTED, []) == ["lender_w1"]
    assert due_followups(d(7), t0, S.SUBMITTED, ["lender_w1"]) == []
    # Down for a month: only the current week, never a burst.
    assert due_followups(d(30), t0, S.APPROVED, []) == ["lender_w4", "borrower_30"]
    assert due_followups(d(31), t0, S.SUBMITTED, ["borrower_30"]) == ["lender_w4"]
    # Borrower check-in is dropped if more than 14 days late.
    assert "borrower_30" not in due_followups(d(45), t0, S.SUBMITTED, [])
    assert "borrower_60" in due_followups(d(61), t0, S.CLOSING, [])
    # Capped at 8 weeks, and closed files get nothing.
    assert not any(k.startswith("lender_") for k in due_followups(d(70), t0, S.SUBMITTED, []))
    for done in (S.FUNDED, S.DECLINED, S.WITHDRAWN, S.PREQUALIFIED):
        assert due_followups(d(30), t0, done, []) == []
    assert due_followups(d(30), None, S.SUBMITTED, []) == []
