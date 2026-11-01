import os

from app.services.credit_service import verify_age, simulate_soft_pull
from app.services.email_service import (
    send_congrats_email,
    send_decline_email,
    send_bank_submission_email,
    send_bank_document_access_email
)
from app.services.eligibility_service import (
    extract_financials,
    has_pfs,
    save_financials,
    evaluate_lenders,
)
from app.services.audit_service import log_event
from app.services.document_vault_service import ingest_application_documents, create_access_grant

COLLECTION_FORM_URL = "https://www.cognitoforms.com/capitalgoose1/documentuploadform"


def process_intake(db, data):
    # STEP 1 - AGE VERIFICATION
    is_eligible = verify_age(data.dob)
    log_event(db, f"Age verification completed for {data.email}")

    # STEP 2 - PASS FLOW (18 or older)
    if is_eligible:
        status = "pre_approved"
        send_congrats_email(data.email, COLLECTION_FORM_URL)
        log_event(db, f"Applicant {data.email} pre-approved - age verified")

    # STEP 3 - FAIL FLOW (under 18)
    else:
        status = "declined"
        send_decline_email(data.email)
        log_event(db, f"Applicant {data.email} declined - failed age verification")

    return status


def process_package(db, application, data):
    soft_pull = simulate_soft_pull(db, application.id)
    log_event(db, f"Soft pull completed for application {application.id} (simulated) — score {soft_pull.credit_score}")

    applicant_state = None
    if isinstance(data, dict):
        applicant_state = data.get("BusinessOperatingState") or data.get("Entry.BusinessOperatingState")

    if not applicant_state:
        log_event(db, f"No business operating state provided for application {application.id}")

    document_urls = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("http"):
                document_urls[key] = value
            elif isinstance(value, dict) and str(value.get("Url", "")).startswith("http"):
                document_urls[key] = value["Url"]

    financials = extract_financials(data)
    if all(financials[k] is None for k in (
        "years_in_business", "annual_revenue", "annual_net_operating_income", "annual_debt_payments"
    )):
        log_event(db, f"No financial fields received for application {application.id} — check the Zapier mapping")
    save_financials(db, application.id, financials)

    eligible = evaluate_lenders(
        db,
        application.id,
        soft_pull.credit_score,
        applicant_state,
        financials,
        has_pfs(document_urls),
    )
    log_event(db, f"Eligibility check for application {application.id}: {len(eligible)} eligible lender(s)")

    if not eligible:
        application.status = "no_lender_match"
        db.commit()
        log_event(db, f"No eligible lender for application {application.id} — see /admin/eligibility/{application.id}")
        return

    matched_bank = eligible[0]

    application.lender = matched_bank.name
    application.status = "submitted"

    if document_urls:
        ingest_application_documents(db, application.id, document_urls)

    # TEST MODE: send the bank notification to a safe test inbox instead
    # of the real bank contact. Turn off by removing TEST_MODE in Railway.
    recipient_email = matched_bank.contact_email
    if os.environ.get("TEST_MODE", "").lower() == "true" and os.environ.get("TEST_RECIPIENT_EMAIL"):
        recipient_email = os.environ["TEST_RECIPIENT_EMAIL"]
        log_event(db, f"TEST MODE: bank notification for {matched_bank.name} redirected to test inbox")

    if recipient_email:
        grant = create_access_grant(db, application.id, recipient_email, recipient_label=matched_bank.name, bank_profile_id=matched_bank.id)
        send_bank_document_access_email(recipient_email, matched_bank.name, grant.code, application.name)
    else:
        log_event(db, f"No contact email configured for lender '{matched_bank.name}' - access grant not created")

    send_bank_submission_email(application.email)
    log_event(db, f"Application {application.id} sent to {matched_bank.name}")
