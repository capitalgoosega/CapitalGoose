# Capital Goose headless engine — partner API (v1, pilot)

Capital Goose is the decision engine behind a partner's own screens. A partner collects the
applicant's consent in their UI, calls us, and gets back a prequalification naming one lender.

## Auth
Send `X-API-Key: cg_<mode>_...` on every `/v1` call. Keys are issued by us
(`POST /admin/partners`), shown once, and stored only as a hash. `sandbox` keys use
**simulated** credit data (random scores — never for real applicants). `live` keys are
refused (503) until a real credit provider is configured (`CREDIT_PROVIDER`).
Limit: 120 requests/minute per partner.

## Submit a referral
`POST /v1/referrals` (optional `Idempotency-Key` header — retries return the original)

```json
{
  "external_ref": "your-own-id",
  "applicant": {"first_name": "", "last_name": "", "email": "", "dob": "YYYY-MM-DD",
                "address": {"street": "", "city": "", "state": "GA", "zip": ""}},
  "business": {"legal_name": "", "state": "GA", "industry": "construction",
               "years_in_business": 5, "annual_revenue": 900000,
               "annual_net_operating_income": 300000, "annual_debt_payments": 100000},
  "loan": {"amount": 250000, "type": "sba_7a"},
  "consent": {"accepted": true, "signer_name": "", "consent_version": "2026-10-v1",
              "captured_at": "2026-11-22T13:00:00Z", "ip_address": "applicant's IP"}
}
```
`consent.accepted` must be `true`; nothing is pulled without it. Under-18 applicants are declined
before any credit pull. DOB and address are used for the check/pull and **not stored**.
The credit score is never returned to partners.

Response: `referral_id`, `status`, `prequalification {matched, lender, likely_range, reasons, blockers}`, `timeline`.
`likely_range` is `null` until lender loan-size ranges are modeled.

## Read status
`GET /v1/referrals/{referral_id}` and `GET /v1/referrals?external_ref=&status=`

Statuses: `received → prequalified → submitted → lender_received → approved → closing → funded`,
with exits `no_match`, `declined`, `withdrawn`.

## Webhooks
If a webhook URL is configured (`PUT /admin/partners/{id}/webhook`, https only, public hosts only),
every status change posts `{"id","type":"referral.<status>","created_at","data":{referral_id,external_ref,status}}`.
Header `X-CapitalGoose-Signature: t=<unix>,v1=<hex>` where `v1 = HMAC_SHA256(secret, "<t>.<raw body>")`.
Reject if `t` is more than 5 minutes old. Any 2xx acknowledges; otherwise we retry
(1m, 5m, 30m, 2h, 12h). Payloads contain ids and status only.

## Internal (X-Admin-Key)
- `POST/GET /admin/partners`, `/{id}/rotate-key`, `/{id}/revoke`, `PUT /{id}/webhook`
- `GET /admin/referrals`, `POST /admin/referrals/{id}/status` (record lender milestones)
- `GET /admin/referrals/metrics/lending-accuracy` — funded ÷ fully submitted, with sample size
- `GET /admin/referrals/webhooks/deliveries`, `POST .../{event_id}/retry`

## Not built yet (next slices)
Real credit provider (CRS/Array), loan-size ranges per lender, hosted pre-qual form + embeddable
widget, document upload through the API, one-tap lender status links, 30/60/90-day borrower
check-ins, partner portal, local-model document extraction, de-identified outcome dataset.
Counsel must sign off on the consent wording, FCRA permissible purpose, and Form 159 terms before any live pull.
