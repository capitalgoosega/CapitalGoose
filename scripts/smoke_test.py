#!/usr/bin/env python3
"""
End-to-end smoke test of the headless engine against a running deployment, using a
SANDBOX partner (simulated credit data; lender emails go only to TEST_RECIPIENT_EMAIL
or are suppressed). It writes clearly labelled test records to that deployment's
database and revokes the test partner at the end.

Usage:
    export ADMIN_API_KEY=...          # the Railway variable; never paste it into chat
    python3 scripts/smoke_test.py https://capitalgoose-production.up.railway.app

Needs only the `requests` package (already in requirements.txt).
"""
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://capitalgoose-production.up.railway.app").rstrip("/")
ADMIN = {"X-Admin-Key": os.environ.get("ADMIN_API_KEY", "")}
PDF = b"%PDF-1.4\n% smoke test file\n"
failures = []


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)
    return ok


def body(first="Smoke", last="Test", amount=250000):
    return {
        "external_ref": "smoke-test",
        "applicant": {"first_name": first, "last_name": last, "email": "smoke-test@example.com",
                      "dob": "1980-01-01",
                      "address": {"street": "1 Test St", "city": "Atlanta", "state": "GA", "zip": "30301"}},
        "business": {"legal_name": "Smoke Test Roofing LLC", "state": "GA", "industry": "construction",
                     "years_in_business": 6, "annual_revenue": 900000,
                     "annual_net_operating_income": 300000, "annual_debt_payments": 100000},
        "loan": {"amount": amount, "type": "sba_7a"},
        "consent": {"accepted": True, "signer_name": "Smoke Test", "consent_version": "smoke-test",
                    "captured_at": datetime.now(timezone.utc).isoformat()},
    }


def main():
    if not ADMIN["X-Admin-Key"]:
        sys.exit("Set ADMIN_API_KEY in your environment first.")

    name = f"Smoke Test {int(time.time())}"
    r = requests.post(f"{BASE}/admin/partners", json={"name": name, "mode": "sandbox"}, headers=ADMIN, timeout=30)
    if not check("create sandbox partner", r.status_code == 201, r.text[:200]):
        sys.exit(1)
    partner = r.json()
    h = {"X-API-Key": partner["api_key"]}

    try:
        check("no key -> 401", requests.get(f"{BASE}/v1/referrals", timeout=30).status_code == 401)
        bad = body(); bad["consent"]["accepted"] = False
        check("consent required (422)", requests.post(f"{BASE}/v1/referrals", json=bad, headers=h, timeout=60).status_code == 422)

        ref = None
        for _ in range(40):   # simulated credit scores are random; retry until a lender matches
            r = requests.post(f"{BASE}/v1/referrals", json=body(), headers=h, timeout=60)
            if r.status_code != 201:
                check("create referral", False, r.text[:200]); break
            if r.json()["status"] == "prequalified":
                ref = r.json(); break
        if not ref:
            check("got a prequalified referral", False, "no lender matched; check lenders/limits via /admin/lenders")
            return
        check("prequalified with a named lender", bool(ref["prequalification"]["lender"]))
        check("credit score not exposed", "credit_score" not in str(ref))
        rid = ref["referral_id"]

        check("exe rejected (415)", requests.put(f"{BASE}/v1/referrals/{rid}/documents/bank_statement?filename=x.exe",
              data=b"MZ not a pdf", headers=h, timeout=60).status_code == 415)
        check("submit blocked while documents missing (422)",
              requests.post(f"{BASE}/v1/referrals/{rid}/submit", headers=h, timeout=60).status_code == 422)
        for t in ("bank_statement", "tax_return", "government_id", "personal_financial_statement"):
            r = requests.put(f"{BASE}/v1/referrals/{rid}/documents/{t}?filename={t}.pdf", data=PDF, headers=h, timeout=60)
            check(f"upload {t}", r.status_code == 201, r.text[:150])

        r = requests.post(f"{BASE}/v1/referrals/{rid}/submit", headers=h, timeout=60)
        check("submit to lender -> submitted", r.status_code == 200 and r.json().get("status") == "submitted", r.text[:200])
        check("submit twice is safe", requests.post(f"{BASE}/v1/referrals/{rid}/submit", headers=h, timeout=60).json().get("idempotent_replay") is True)

        for st in ("approved", "closing", "funded"):
            r = requests.post(f"{BASE}/admin/referrals/{rid}/status", json={"status": st}, headers=ADMIN, timeout=60)
            check(f"admin milestone -> {st}", r.status_code == 200, r.text[:150])
        check("cannot go backwards (409)", requests.post(f"{BASE}/admin/referrals/{rid}/status",
              json={"status": "approved"}, headers=ADMIN, timeout=60).status_code == 409)

        m = requests.get(f"{BASE}/admin/referrals/metrics/lending-accuracy", headers=ADMIN, timeout=30).json()
        check("lending-accuracy metric counts the funded referral", m.get("funded", 0) >= 1)

        # hosted widget
        s = requests.post(f"{BASE}/v1/widget-sessions", headers=h, timeout=30,
                          json={"external_ref": "smoke-widget", "allowed_origin": "https://example.com",
                                "prefill": {"first_name": "Smoke"}})
        if check("create widget session", s.status_code == 201, s.text[:200]):
            tok = s.json()["token"]
            page = requests.get(f"{BASE}/widget/{tok}", timeout=30)
            check("widget form renders with strict CSP", page.status_code == 200 and "frame-ancestors https://example.com" in page.headers.get("content-security-policy", ""))
            check("widget shows consent version text", "electronic signature" in page.text)
            w = body(); payload = {"applicant": w["applicant"], "business": w["business"], "loan": w["loan"],
                                   "signer_name": "Smoke Test", "consent_accepted": True}
            check("widget submit ok", requests.post(f"{BASE}/widget/{tok}/submit", json=payload, timeout=60).status_code == 200)
            check("widget token is single use (409)", requests.post(f"{BASE}/widget/{tok}/submit", json=payload, timeout=60).status_code == 409)

        print("\nLender emails (if any) went to TEST_RECIPIENT_EMAIL, never to a real lender.")
    finally:
        r = requests.post(f"{BASE}/admin/partners/{partner['id']}/revoke", headers=ADMIN, timeout=30)
        print(f"test partner revoked: {r.status_code == 200}")
    print("\nALL CHECKS PASSED" if not failures else f"\n{len(failures)} CHECK(S) FAILED: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
