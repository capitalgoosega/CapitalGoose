import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from app.core.config import settings

def send_email(to, subject, body):
    print(f"ATTEMPTING TO SEND EMAIL TO: {to}")
    print(f"SENDGRID_API_KEY: {settings.sendgrid_api_key}")
    print(f"SENDER_EMAIL: {settings.sender_email}")
    try:
        message = Mail(
            from_email=settings.sender_email,
            to_emails=to,
            subject=subject,
            plain_text_content=body
        )
        sg = SendGridAPIClient(settings.sendgrid_api_key)
        response = sg.send(message)
        print(f"EMAIL STATUS CODE: {response.status_code}")
    except Exception as e:
        print(f"EMAIL ERROR: {e}")


def send_congrats_email(to, collection_form_url):
    send_email(
        to,
        " Capital Goose — You’re Pre-Approved (Next Steps Required)",
        f"""Dear Applicant,

Good news — your application has passed our initial review and is pre-approved.

Based on the information you submitted, you meet the preliminary criteria for financing. To move forward, we need to verify a few final details and collect supporting documentation.

To continue your application, please upload your documents here:
Secure Document Upload⁠

Once received, our team will complete final verification and match you with the best available lending options.

If you have questions, simply reply to this email.

— Capital Goose"""
    )


def send_decline_email(to):
    send_email(
        to,
        "An Update on Your Loan Application",
        """Dear Applicant,

Thank you for choosing Capitol Goose and for taking the time to submit your loan application. We genuinely appreciate the trust you've placed in us.

After a thorough review of your application, we regret to inform you that we are unable to approve your request at this time. Unfortunately, you do not meet the minimum age requirement of 18 years old to qualify for a loan with Capitol Goose.

We encourage you to reapply once you meet the eligibility requirements.

Thank you again for considering Capitol Goose. We're rooting for your success.

Sincerely,
The Capitol Goose Team"""
    )


def send_bank_submission_email(to):
    send_email(
        to,
        "Your Application Has Been Submitted to Our Lending Partners",
        """Dear Applicant,

We're reaching out to let you know that your completed loan application has been successfully submitted to our network of lending partners for final review.

From here, our team will be working diligently behind the scenes to match you with the best possible lending option based on your profile and needs. You can expect to hear back with a final decision within 5 to 7 business days.

We want to take a moment to sincerely thank you for choosing Capitol Goose Fintech. It means a great deal to us, and we are fully committed to making this process as smooth and stress-free as possible for you.

If you have any questions while you wait or need to update any information, please don't hesitate to reach out to us directly. We're always happy to help.

Warm regards,
The Capitol Goose Team"""
    )
