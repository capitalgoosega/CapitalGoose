# Capital Goose — headless funding engine

Capital Goose sits inside other companies' apps (contractor software, CPAs, chambers).
When a customer taps "see what you qualify for," the engine:

1. collects consent,
2. runs a credit step (self-reported ranges today; a real provider later),
3. matches ONE best-fit lender,
4. collects documents,
5. hands the file to the lender and tracks it to **funded**,
6. follows up automatically and reports a lending-accuracy metric (goal: 50%).

Partners reach it through a REST API (`/v1`) or an embeddable hosted widget.

## Start here

Read **[docs/HEADLESS_API.md](docs/HEADLESS_API.md)** — it covers auth, referrals, the widget,
documents, webhooks, follow-ups, outcomes and the demo.

## Run it locally

Use Python 3.12 or 3.13 (not an alpha build).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

It uses a local SQLite file by default. Production uses Postgres via `DATABASE_URL`.

## Tests

```bash
pytest tests/test_engine_pure.py        # fast, no server needed
pytest tests/test_headless_api.py       # integration tests (never run in CI yet)
```

`scripts/smoke_test.py` runs an end-to-end check against a deployment using a sandbox partner.
It needs `ADMIN_API_KEY` in your environment. Never paste keys into chat or commit them.

## Demo app

Set `DEMO_ENABLED=true` and open `/demo` for a fake partner app that calls the real API.
Keep it off in production unless you are showing it.

## Layout

| Path | What it holds |
| --- | --- |
| `app/api/` | HTTP routes: partner API, widget, check-in, admin, demo |
| `app/engine/` | Business logic: referrals, consent, credit, documents, handoff, follow-ups |
| `app/models/`, `app/schemas/` | Database tables and request/response shapes |
| `app/services/` | Email sending |
| `docs/` | API documentation |
| `scripts/` | Smoke test and webhook test helpers |
| `tests/` | Pure and integration tests |

## Key settings (environment variables)

`DATABASE_URL`, `ADMIN_API_KEY`, `CREDIT_PROVIDER` (`self_reported` or `simulated`),
`CONSENT_TEXT_APPROVED`, `DEMO_ENABLED`, `SENDER_EMAIL`, `REPLY_TO_EMAIL`,
`TEST_MODE`, `TEST_RECIPIENT_EMAIL`, `DOCUMENT_ENCRYPTION_KEY`, `DISABLE_FOLLOWUPS`.

## Working rules

- Work in a branch and open a pull request; do not push to `main`.
- Do not change anything in Railway (production) without asking.
- Never use real customer data in development or tests.
- Never commit secrets. Keys live in Railway variables.
