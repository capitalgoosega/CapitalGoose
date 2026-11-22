"""
End-to-end test of the partner API against a throwaway SQLite database.
Skipped automatically where FastAPI/SQLAlchemy aren't installed.
"""
import os
import tempfile
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["DOCUMENT_ENCRYPTION_KEY"] = "WZ5vNlo4JqkJ2m6n2XQ8gXx0bq0H0m1y8o9K1b2c3d4="  # test-only Fernet key
os.environ["CREDIT_PROVIDER"] = "simulated"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
ADMIN = {"X-Admin-Key": os.environ["ADMIN_API_KEY"]}


def _payload(**over):
    body = {
        "external_ref": "job-123",
        "applicant": {
            "first_name": "Test", "last_name": "Owner", "email": "owner@example.com",
            "dob": "1980-01-01",
            "address": {"street": "1 Main St", "city": "Atlanta", "state": "GA", "zip": "30301"},
        },
        "business": {
            "legal_name": "Test Roofing LLC", "state": "GA", "industry": "construction",
            "years_in_business": 5, "annual_revenue": 900000,
            "annual_net_operating_income": 300000, "annual_debt_payments": 100000,
        },
        "loan": {"amount": 250000, "type": "sba_7a"},
        "consent": {
            "accepted": True, "signer_name": "Test Owner", "consent_version": "2026-10-v1",
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    body.update(over)
    return body


@pytest.fixture(scope="module")
def sandbox_key():
    r = client.post("/admin/partners", json={"name": "Test Partner"}, headers=ADMIN)
    assert r.status_code == 201, r.text
    assert r.json()["api_key"].startswith("cg_sandbox_")
    return r.json()["api_key"]


def test_requires_api_key():
    assert client.post("/v1/referrals", json=_payload()).status_code == 401
    assert client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": "nope"}).status_code == 401


def test_consent_is_mandatory(sandbox_key):
    bad = _payload()
    bad["consent"]["accepted"] = False
    r = client.post("/v1/referrals", json=bad, headers={"X-API-Key": sandbox_key})
    assert r.status_code == 422


def test_referral_lifecycle_and_idempotency(sandbox_key):
    h = {"X-API-Key": sandbox_key, "Idempotency-Key": "abc-1"}
    r = client.post("/v1/referrals", json=_payload(), headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] in ("prequalified", "no_match")   # simulated score is random
    assert "credit_score" not in str(body)                  # never expose the score
    ref_id = body["referral_id"]

    replay = client.post("/v1/referrals", json=_payload(), headers=h).json()
    assert replay["referral_id"] == ref_id and replay["idempotent_replay"] is True

    got = client.get(f"/v1/referrals/{ref_id}", headers={"X-API-Key": sandbox_key})
    assert got.status_code == 200 and got.json()["timeline"][0]["status"] == "received"


def test_under_18_is_declined_without_a_pull(sandbox_key):
    young = _payload()
    young["applicant"]["dob"] = f"{datetime.now().year - 10}-01-01"
    r = client.post("/v1/referrals", json=young, headers={"X-API-Key": sandbox_key})
    assert r.status_code == 201 and r.json()["status"] == "declined"


def test_partners_cannot_see_each_others_referrals(sandbox_key):
    other = client.post("/admin/partners", json={"name": "Other Partner"}, headers=ADMIN).json()["api_key"]
    ref_id = client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": sandbox_key}).json()["referral_id"]
    assert client.get(f"/v1/referrals/{ref_id}", headers={"X-API-Key": other}).status_code == 404


def test_live_key_refused_while_credit_provider_is_simulated():
    live = client.post("/admin/partners", json={"name": "Live Partner", "mode": "live"}, headers=ADMIN).json()["api_key"]
    r = client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": live})
    assert r.status_code == 503


def test_admin_milestones_and_accuracy(sandbox_key):
    ref_id = None
    for _ in range(40):  # simulated scores are random; find one that prequalifies
        body = client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": sandbox_key}).json()
        if body["status"] == "prequalified":
            ref_id = body["referral_id"]
            break
    if ref_id is None:
        pytest.skip("no seeded lender matched this profile")
    for st in ("submitted", "approved", "closing", "funded"):
        r = client.post(f"/admin/referrals/{ref_id}/status", json={"status": st}, headers=ADMIN)
        assert r.status_code == 200, r.text
    assert client.post(f"/admin/referrals/{ref_id}/status", json={"status": "approved"}, headers=ADMIN).status_code == 409
    m = client.get("/admin/referrals/metrics/lending-accuracy", headers=ADMIN).json()
    assert m["funded"] >= 1 and m["sample_is_small"] is True


def test_revoked_key_stops_working():
    created = client.post("/admin/partners", json={"name": "Temp Partner"}, headers=ADMIN).json()
    key = created["api_key"]
    assert client.get("/v1/referrals", headers={"X-API-Key": key}).status_code == 200
    client.post(f"/admin/partners/{created['id']}/revoke", headers=ADMIN)
    assert client.get("/v1/referrals", headers={"X-API-Key": key}).status_code == 401


# ---- documents, handoff, lender status link ----------------------------------
import re  # noqa: E402

PDF = b"%PDF-1.4\n% test file\n"


def _prequalified(key):
    for _ in range(60):
        body = client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": key}).json()
        if body["status"] == "prequalified":
            return body["referral_id"]
    pytest.skip("no seeded lender matched this profile")


def test_upload_validation_and_submit_requires_documents(sandbox_key, monkeypatch):
    sent = []
    monkeypatch.setattr("app.engine.handoff_service.send_lender_handoff_email", lambda *a: sent.append(a))
    h = {"X-API-Key": sandbox_key}
    ref = _prequalified(sandbox_key)

    bad = client.put(f"/v1/referrals/{ref}/documents/bank_statement?filename=x.exe", content=b"MZ not a pdf", headers=h)
    assert bad.status_code == 415
    assert client.put(f"/v1/referrals/{ref}/documents/nonsense?filename=x.pdf", content=PDF, headers=h).status_code == 422

    assert client.post(f"/v1/referrals/{ref}/submit", headers=h).status_code == 422   # nothing uploaded yet
    ok = client.put(f"/v1/referrals/{ref}/documents/bank_statement?filename=jan.pdf", content=PDF, headers=h)
    assert ok.status_code == 201 and "bank_statement" not in ok.json()["missing"]
    assert sent == []   # nothing emailed before submit


def test_full_handoff_and_lender_link_flow(sandbox_key, monkeypatch):
    sent = []
    monkeypatch.setattr("app.engine.handoff_service.send_lender_handoff_email", lambda *a: sent.append(a))
    monkeypatch.setenv("TEST_RECIPIENT_EMAIL", "inbox@example.com")   # sandbox referrals go here, never to a lender
    h = {"X-API-Key": sandbox_key}
    ref = _prequalified(sandbox_key)
    for t in ("bank_statement", "tax_return", "government_id", "personal_financial_statement"):
        assert client.put(f"/v1/referrals/{ref}/documents/{t}?filename={t}.pdf", content=PDF, headers=h).status_code == 201

    r = client.post(f"/v1/referrals/{ref}/submit", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "submitted"
    assert client.post(f"/v1/referrals/{ref}/submit", headers=h).json()["idempotent_replay"] is True
    assert len(sent) == 1 and sent[0][0] == "inbox@example.com"
    token = re.search(r"/lender-status/([\w-]+)", sent[0][3]).group(1)

    # GET only shows the page; it must not change anything (email scanners open links).
    page = client.get(f"/lender-status/{token}")
    assert page.status_code == 200 and "no-store" in page.headers["cache-control"]
    assert client.get(f"/v1/referrals/{ref}", headers=h).json()["status"] == "submitted"

    assert client.post(f"/lender-status/{token}", content="status=declined").status_code == 422   # reason required
    assert client.post(f"/lender-status/{token}", content="status=approved").status_code == 200
    assert client.post(f"/lender-status/{token}", content="status=lender_received").status_code == 409   # no going back
    done = client.post(f"/lender-status/{token}", content="status=declined&reason_code=collateral")
    assert done.status_code == 200
    assert client.get(f"/lender-status/{token}").status_code == 404   # link retired after a final outcome
    assert client.get("/lender-status/not-a-real-token").status_code == 404

    m = client.get("/admin/referrals/metrics/lending-accuracy", headers=ADMIN).json()
    assert m["decline_reasons"].get("collateral", 0) >= 1


# ---- loan range + hosted widget ----------------------------------------------
import json  # noqa: E402


def test_likely_range_appears_when_lender_has_limits(sandbox_key):
    lenders = client.get("/admin/lenders/", headers=ADMIN).json()["lenders"]
    for l in lenders:
        client.patch(f"/admin/lenders/{l['id']}", json={"min_loan_amount": 50000, "max_loan_amount": 500000}, headers=ADMIN)
    assert client.patch(f"/admin/lenders/{lenders[0]['id']}",
                        json={"min_loan_amount": 9, "max_loan_amount": 1}, headers=ADMIN).status_code == 422
    for _ in range(60):
        body = client.post("/v1/referrals", json=_payload(), headers={"X-API-Key": sandbox_key}).json()
        if body["status"] == "prequalified":
            assert body["prequalification"]["likely_range"] == {"min": 50000, "max": 500000}
            break
    big = _payload()
    big["loan"]["amount"] = 5_000_000
    assert client.post("/v1/referrals", json=big, headers={"X-API-Key": sandbox_key}).json()["status"] == "no_match"


def _widget_body(**over):
    p = _payload()
    body = {"applicant": p["applicant"], "business": p["business"], "loan": p["loan"],
            "signer_name": "Test Owner", "consent_accepted": True}
    body.update(over)
    return body


def test_widget_session_and_submit_flow(sandbox_key):
    h = {"X-API-Key": sandbox_key}
    assert client.post("/v1/widget-sessions", json={"prefill": {"ssn": "1"}}, headers=h).status_code == 422
    assert client.post("/v1/widget-sessions", json={"allowed_origin": "https://evil.com/x"}, headers=h).status_code == 422

    s = client.post("/v1/widget-sessions", headers=h, json={
        "external_ref": "w-1", "allowed_origin": "https://app.partner.com", "prefill": {"first_name": "Pat"}})
    assert s.status_code == 201, s.text
    token = s.json()["token"]

    page = client.get(f"/widget/{token}")
    assert page.status_code == 200 and "Pat" in page.text
    csp = page.headers["content-security-policy"]
    assert "frame-ancestors https://app.partner.com" in csp and "unsafe-inline" not in csp
    assert "style=" not in page.text.replace("style nonce", "")        # CSP blocks inline style attributes

    assert client.post(f"/widget/{token}/submit", json=_widget_body(consent_accepted=False)).status_code == 422
    done = client.post(f"/widget/{token}/submit", json=_widget_body())
    assert done.status_code == 200, done.text
    assert client.post(f"/widget/{token}/submit", json=_widget_body()).status_code == 409   # single use

    result = client.get(f"/widget/{token}")
    assert result.status_code == 200 and ("may qualify" in result.text or "couldn't match" in result.text)
    refs = client.get("/v1/referrals?external_ref=w-1", headers=h).json()["referrals"]
    assert len(refs) == 1


def test_widget_bad_tokens_and_embed_script():
    assert client.get("/widget/not-a-token").status_code == 404
    assert client.post("/widget/not-a-token/submit", json={}).status_code == 404
    js = client.get("/widget/embed.js")
    assert js.status_code == 200 and "CapitalGooseWidget" in js.text


def test_live_widget_sessions_blocked_until_consent_text_approved(monkeypatch):
    monkeypatch.delenv("CONSENT_TEXT_APPROVED", raising=False)
    live = client.post("/admin/partners", json={"name": "Live Widget Partner", "mode": "live"}, headers=ADMIN).json()["api_key"]
    assert client.post("/v1/widget-sessions", json={}, headers={"X-API-Key": live}).status_code == 503
