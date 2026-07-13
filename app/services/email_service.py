import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings


def send_email(to, subject, body, html=False):
    print(f"ATTEMPTING TO SEND EMAIL TO: {to}")
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.sender_email
        msg["To"] = to
        msg["Subject"] = subject

        if html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_user, settings.gmail_app_password)
            server.sendmail(settings.sender_email, to, msg.as_string())

        print("EMAIL SENT SUCCESSFULLY")

    except Exception as e:
        print(f"EMAIL ERROR: {e}")


def send_congrats_email(to, collection_form_url):
    print(f"ATTEMPTING TO SEND EMAIL TO: {to}")
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = settings.sender_email
        msg["To"] = to
        msg["Subject"] = "Capital Goose — You're Pre-Qualified (Next Steps Required)"

        plain = f"Please upload your documents here: {collection_form_url}"

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

        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_user, settings.gmail_app_password)
            server.sendmail(settings.sender_email, to, msg.as_string())

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
The Capitol Goose Fintech Team"""
    )
