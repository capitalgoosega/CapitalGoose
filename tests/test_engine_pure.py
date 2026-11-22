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
