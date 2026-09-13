from app.services.credit_service import verify_age, simulate_soft_pull
from app.services.email_service import (
    send_congrats_email,
    send_decline_email,
    send_bank_submission_email,
    send_bank_document_access_email
)
from app.services.lender_service import choose_lender
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

    matched_bank = choose_lender(db, application.loan_type, soft_pull.credit_score)

    if not matched_bank:
        application.status = "no_lender_match"
        db.commit()
        log_event(db, f"No lender match found for application {application.id} — score {soft_pull.credit_score}, loan_type {application.loan_type}")
        return

    application.lender = matched_bank.name
    application.status = "submitted"

    document_urls = {}
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("http"):
                document_urls[key] = value
            elif isinstance(value, dict) and str(value.get("Url", "")).startswith("http"):
                document_urls[key] = value["Url"]

    if document_urls:
        ingest_application_documents(db, application.id, document_urls)

    if matched_bank.contact_email:
        grant = create_access_grant(db, application.id, matched_bank.contact_email, recipient_label=matched_bank.name)
        send_bank_document_access_email(matched_bank.contact_email, matched_bank.name, grant.code, application.name)
    else:
        log_event(db, f"No contact email configured for lender '{matched_bank.name}' - access grant not created")

    send_bank_submission_email(application.email)
    log_event(db, f"Application {application.id} sent to {matched_bank.name}")
