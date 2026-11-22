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
