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
`likely_range` is `{min,max}` from the matched lender's loan-size limits, or `null` when none are configured
(set them with `PATCH /admin/lenders/{id}` `min_loan_amount` / `max_loan_amount`; unset = not enforced).

## Read status
`GET /v1/referrals/{referral_id}` and `GET /v1/referrals?external_ref=&status=`

Statuses: `received → prequalified → submitted → lender_received → approved → closing → funded`,
with exits `no_match`, `declined`, `withdrawn`.

## Hosted form + embeddable widget
For partners with no UI of their own, or who want the consent screen to be ours.

1. **Your server** calls `POST /v1/widget-sessions` with your API key and optional
   `{external_ref, allowed_origin: "https://app.yoursite.com", prefill: {first_name, last_name, email, legal_name, state, years_in_business, annual_revenue, loan_amount, loan_type}}`.
   It returns a single-use `token` (valid 30 minutes), `embed_url` and `script_url`.
2. **The browser** never sees your API key. Embed with either an iframe on `embed_url`, or:
   ```html
   <div id="cg"></div>
   <script src="https://<host>/widget/embed.js"></script>
   <script>CapitalGooseWidget.mount(document.getElementById('cg'),
     {token: '<token>', onResult: function (r) { /* {referralId, status, matched} */ }});</script>
   ```
   `allowed_origin` is required to frame the widget (it sets `frame-ancestors` and the postMessage target);
   without it the page only works as a full-page link.
3. The applicant fills the form and agrees to **our** consent text (we record our wording version, the time and
   the IP — the browser can't supply them). The referral is created under your partner and the result page is shown.
   Check status with `GET /v1/referrals?external_ref=...` or webhooks, then continue with documents + submit.

Live partners can't mint sessions until `CONSENT_TEXT_APPROVED=true` is set — only after counsel approves the
wording in `app/engine/consent.py` (it is a placeholder today).

## Documents and handoff
Once a referral is `prequalified`:

- `PUT /v1/referrals/{id}/documents/{doc_type}?filename=jan.pdf` — raw file bytes as the body
  (PDF, PNG or JPEG, max 15 MB, 20 files). `doc_type`: `bank_statement`, `tax_return`, `government_id`,
  `personal_financial_statement`, `other`. Files are checked by their real header bytes and stored encrypted.
- `GET /v1/referrals/{id}/documents` — what's uploaded, what's required, what's `missing`
  (the Personal Financial Statement is required only if the matched lender requires it).
- `POST /v1/referrals/{id}/submit` — says the file is complete. We email the matched lender a portal access
  code and a private status link (no applicant data in the email), and the referral becomes `submitted`.
  Safe to call twice. `422` lists missing documents.

**Sandbox keys never contact real lenders**: the handoff goes to `TEST_RECIPIENT_EMAIL`, or is suppressed if unset.

## Lender status links
The handoff email contains a private link. The page only *shows* status on GET (so email scanners can't change
anything); the lender presses a button — received / approved / closing / funded / declined — to record it.
Declines require a reason (credit, cash flow, collateral, time in business, documentation, policy, applicant
stopped responding, other). The link is retired after funded/declined. Reasons appear in
`GET /admin/referrals/metrics/lending-accuracy` under `decline_reasons` — the data for tuning lender rules.
`POST /admin/referrals/{id}/resend-handoff` issues a fresh code + link and revokes the old ones.

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
widget (needs short-lived widget tokens so API keys never sit in a browser), automated weekly lender
follow-ups, 30/60/90-day borrower check-ins, partner portal, local-model document extraction, de-identified outcome dataset.
Counsel must sign off on the consent wording, FCRA permissible purpose, and Form 159 terms before any live pull.
