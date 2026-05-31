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
        "You're Pre-Approved — Complete Your Application",
        f"""Dear Applicant,

We have great news! After reviewing your application, Capitol Goose is pleased to inform you that you have been pre-approved for your loan!

This is a big step, and we're excited to help you move forward. To finalize your application, please complete the next stage of the process by filling out additional using the link below:

{collection_form_url}

Please complete this form at your earliest convenience so we can match you with the right lending partner and keep your application moving without delay.

If you have any questions or need assistance along the way, our team is always here to help.

Warm regards,
The Capitol Goose Fintech Team"""
    )


def send_decline_email(to, score):
    send_email(
        to,
        "An Update on Your Loan Application",
        f"""Dear Applicant,

Thank you for choosing Capitol Goose Fintech and for taking the time to submit your loan application. We genuinely appreciate the trust you've placed in us.

After a thorough review of your application, we regret to inform you that we are unable to approve your request at this time. The primary factor in this decision was your current credit score of {score}, which fell below our minimum approval threshold.

We know this isn't the news you were hoping for, and we want to be as helpful as possible in getting you to where you need to be. Here are some steps you can take to strengthen your application before reapplying:

  - Focus on paying down existing balances to lower your credit utilization
  - Make sure all bills, loans, and obligations are paid on time going forward
  - Avoid applying for new lines of credit in the near future
  - Review your credit report for any errors or inaccuracies and dispute them promptly
  - Give your credit profile at least 6 months to reflect these improvements

We encourage you to reapply in 6 months. A lot can change in that time, and we would love the opportunity to work with you when you're ready.

Thank you again for considering Capitol Goose Fintech. We're rooting for your success.

Sincerely,
The Capitol Goose Fintech Team"""
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
The Capitol Goose Fintech Team"""
    )