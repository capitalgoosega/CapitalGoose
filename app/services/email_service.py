import base64
import smtplib
import ssl
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_SEND_URL = "https://www.googleapis.com/gmail/v1/users/me/messages/send"


def _get_access_token():
    response = requests.post(
        GMAIL_TOKEN_URL,
        data={
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "refresh_token": settings.gmail_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _build_message(to, subject, body, html=False):
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["subject"] = subject
    # With SMTP (Titan) the From address is real. With the Gmail API it only takes effect if
    # Gmail has the address set up as a "Send mail as" alias (otherwise Gmail keeps its own).
    if settings.sender_email:
        message["from"] = f"Capital Goose <{settings.sender_email}>"
    # A no-reply sender still needs replies to land somewhere a person reads.
    if settings.reply_to_email:
        message["reply-to"] = settings.reply_to_email
    message.attach(MIMEText(body, "html" if html else "plain"))
    return message


def smtp_configured():
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def _send_via_smtp(message):
    port = settings.smtp_port
    from_addr = settings.sender_email or settings.smtp_user
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(settings.smtp_host, port, context=context, timeout=15) as server:
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message, from_addr=from_addr)
    else:
        with smtplib.SMTP(settings.smtp_host, port, timeout=15) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message, from_addr=from_addr)


def _send_via_gmail(message):
    access_token = _get_access_token()
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    response = requests.post(
        GMAIL_SEND_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"raw": raw},
        timeout=10,
    )
    response.raise_for_status()


def resend_configured():
    return settings.email_provider == "resend" and bool(settings.resend_api_key and settings.sender_email)


def _send_via_resend(to, subject, body, html=False):
    """Resend's HTTPS API. Works on hosts that block SMTP. The sender domain must be verified in Resend."""
    payload = {
        "from": f"Capital Goose <{settings.sender_email}>",
        "to": [to],
        "subject": subject,
        "html" if html else "text": body,
    }
    if settings.reply_to_email:
        payload["reply_to"] = settings.reply_to_email
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        json=payload,
        timeout=10,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend {response.status_code}: {response.text[:200]}")


def _deliver(to, subject, body, html=False):
    """Send via Resend when EMAIL_PROVIDER=resend, else SMTP if configured, else the Gmail API.
    If the preferred route fails, fall back to Gmail so a lender email is never lost."""
    message = _build_message(to, subject, body, html=html)
    try:
        if resend_configured():
            _send_via_resend(to, subject, body, html=html)
            return
        if smtp_configured():
            _send_via_smtp(message)
            return
    except Exception as e:
        print(f"EMAIL primary route failed ({e}); falling back to Gmail")
    _send_via_gmail(message)


def send_email(to, subject, body, html=False):
    print(f"ATTEMPTING TO SEND EMAIL TO: {to}")
    try:
        _deliver(to, subject, body, html=html)
        print("EMAIL SENT SUCCESSFULLY")
    except Exception as e:
        print(f"EMAIL ERROR: {e}")


def send_congrats_email(to, collection_form_url):
    print(f"ATTEMPTING TO SEND EMAIL TO: {to}")
    try:
        html = f"""<!DOCTYPE html>
<html>
<body style="font-family: Arial, sans-serif; color: #222; line-height: 1.6; font-size: 16px;">
  <p>Dear Applicant,</p>
  <p>Thank you for submitting your application with <strong>Capital Goose</strong>.</p>
  <p>
    Based on the information you provided, your application has met our initial
    qualification criteria and is eligible to move to the next stage of our review process.
  </p>
  <p>
    To continue, we need to verify your information and collect a few supporting
    documents required by our lending partners.
  </p>
  <p>Please securely upload your requested documents here:</p>
  <p>
    <a href="{collection_form_url}"
       style="color: #0b57d0; font-weight: bold;">
      Secure Document Upload
    </a>
  </p>
  <p>
    Once we receive your documentation, our team will complete the verification process
    and match your application with the most appropriate lending opportunities available.
  </p>
  <p>
    <strong>Please note:</strong> Meeting our initial qualification criteria is not a loan
    approval or commitment to lend. Final lending decisions are made after document
    verification and lender underwriting.
  </p>
  <p>If you have any questions, simply reply to this email — we're happy to help.</p>
  <p>
    Thank you,<br>
    The Capital Goose Team
  </p>
</body>
</html>"""

        _deliver(
            to,
            "Capital Goose — You're Pre-Qualified (Next Steps Required)",
            html,
            html=True,
        )
        print("EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        print(f"EMAIL ERROR: {e}")


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


def send_bank_document_access_email(recipient_email, recipient_label, code, applicant_name):
    # Uses the CTO's banking partner email template. The applicant's name is
    # intentionally left out: no applicant information goes in this email.
    # recipient_label and applicant_name stay in the signature so
    # workflow_service.py doesn't need to change.
    portal_url = f"https://capitalgoose-production.up.railway.app/bank-portal/access?code={code}"
    body = (
        "Hello,\n\n"
        "Capital Goose has identified a new qualified applicant for your institution.\n\n"
        "The applicant's collection package is now available for your review through our secure document portal.\n\n"
        f"Access Code: {code}\n\n"
        f"Access Collection Package: {portal_url}\n\n"
        "Please visit the link above and enter your access code to securely retrieve the applicant's information and supporting documentation.\n\n"
        "If you have any questions or experience issues accessing the collection package, please contact the Capital Goose team.\n\n"
        "Best regards,\n\n"
        "Capital Goose Team"
    )
    send_email(
        recipient_email,
        "New Qualified Applicant from Capital Goose – Access Code Available",
        body,
    )


def send_bank_invitation_email(recipient_email, activation_url, bank_name, expires_hours=72):
    body = (
        "Hello,\n\n"
        f"Capital Goose has created a secure portal account for {bank_name}.\n\n"
        "To activate your account, use the link below to choose your password and set up "
        "an authenticator app for two-step sign-in:\n\n"
        f"{activation_url}\n\n"
        f"This link can be used once and expires in {expires_hours} hours. "
        "We will never email you a password.\n\n"
        "If you were not expecting this invitation, please ignore this email or contact the "
        "Capital Goose team.\n\n"
        "Best regards,\n\n"
        "Capital Goose Team"
    )
    send_email(
        recipient_email,
        "Capital Goose – Activate Your Secure Portal Account",
        body,
    )


def send_lender_handoff_email(recipient_email, bank_name, code, status_url):
    # No applicant information in the email: the file is behind the portal login.
    portal_url = f"https://capitalgoose-production.up.railway.app/bank-portal/access?code={code}"
    body = (
        "Hello,\n\n"
        "Capital Goose has a completed, pre-screened application ready for your review.\n\n"
        f"Access Code: {code}\n\n"
        f"Review the file in the secure portal: {portal_url}\n\n"
        "When you have an update, you can report it in one step - no login needed. "
        "This link is private to this application; please do not forward it:\n\n"
        f"{status_url}\n\n"
        "Updates we ask for: file received, approved, closing, funded, or declined "
        "(with a reason). They help us send you better-matched files.\n\n"
        "Best regards,\n\n"
        "Capital Goose Team"
    )
    send_email(
        recipient_email,
        "New Qualified Applicant from Capital Goose - Ready for Review",
        body,
    )


def send_lender_reminder_email(recipient_email, bank_name, reference, status_url, weeks_open):
    # Reference id only; no applicant details in email.
    body = (
        "Hello,\n\n"
        f"A quick check on file {reference}, sent to {bank_name} about {weeks_open} week(s) ago.\n\n"
        "One tap tells us where it stands (received, approved, closing, funded or declined). "
        "This link is private to this file; please do not forward it:\n\n"
        f"{status_url}\n\n"
        "Thank you,\n\n"
        "Capital Goose Team"
    )
    send_email(recipient_email, f"Status check: Capital Goose file {reference}", body)


def send_borrower_checkin_email(recipient_email, first_name, lender_name, checkin_url, days):
    body = (
        f"Hi {first_name},\n\n"
        f"About {days} days ago we sent your loan file to {lender_name}. "
        "We'd like to know how it's going, and it takes one tap:\n\n"
        f"{checkin_url}\n\n"
        "If you would rather not get these check-ins, just reply and let us know.\n\n"
        "Capital Goose Team"
    )
    send_email(recipient_email, "How is your loan going?", body)
