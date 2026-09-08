import os
import smtplib
from email.mime.text import MIMEText

# -----------------------------------
# EMAIL DELIVERY
# -----------------------------------

def send_email(receiver_email, subject, body):
    sender_email = os.getenv("SMTP_SENDER_EMAIL", "").strip()
    app_password = "".join(os.getenv("SMTP_APP_PASSWORD", "").split())
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender_email or not app_password:
        raise RuntimeError(
            "Email OTP delivery is not configured. Set SMTP_SENDER_EMAIL and SMTP_APP_PASSWORD."
        )

    message = MIMEText(str(body or ""), "plain", "utf-8")
    message["Subject"] = str(subject or "")
    message["From"] = sender_email
    message["To"] = str(receiver_email or "").strip()

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(sender_email, app_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise RuntimeError("The verification email could not be sent.") from error