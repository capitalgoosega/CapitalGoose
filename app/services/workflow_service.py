from app.services.credit_service import run_credit_pull, smart_quality_process
from app.services.email_service import (
    send_congrats_email,
    send_decline_email,
    send_bank_submission_email
)
from app.services.lender_service import choose_lender
from app.services.audit_service import log_event

PASSING_SCORE = 650
COLLECTION_FORM_URL = "https://www.cognitoforms.com/capitalgoose1/documentuploadform"


def process_intake(db, data):
    # STEP 1 — ISOFTPULL API
    score = run_credit_pull()
    log_event(db, f"ISOFTPULL completed for {data.email}")

    # STEP 2 — SMART QUALITY PROCESS
    quality_result = smart_quality_process(score)
    passed = quality_result["passed"]

    # STEP 3 — PASS FLOW
    if passed:
        status = "pre_approved"
        send_congrats_email(data.email, COLLECTION_FORM_URL)
        log_event(db, f"Applicant {data.email} pre-approved with score {score}")

    # STEP 4 — FAIL FLOW
    else:
        status = "declined"
        send_decline_email(data.email, score)
        log_event(db, f"Applicant {data.email} declined with score {score}")

    return score, status


def process_package(db, application, data):
    lender = choose_lender(data.loan_type, application.credit_score)
    application.lender = lender
    application.status = "submitted"
    send_bank_submission_email(application.email)
    log_event(db, f"Application {application.id} sent to {lender}")
    return
