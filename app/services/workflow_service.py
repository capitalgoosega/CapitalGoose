from app.services.credit_service import verify_age
from app.services.email_service import (
    send_congrats_email,
    send_decline_email,
    send_bank_submission_email
)
from app.services.lender_service import choose_lender
from app.services.audit_service import log_event

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
    from app.services.lender_service import choose_lender
    lender = choose_lender(application.loan_type, 700)
    application.lender = lender
    application.status = "submitted"
    send_bank_submission_email(application.email)
    log_event(db, f"Application {application.id} sent to {lender}")
    return
