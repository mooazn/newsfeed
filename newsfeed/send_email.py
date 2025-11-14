import smtplib
from email.mime.text import MIMEText
import os

from .logging_setup import setup_logger

logger = setup_logger()


def send_via_gmail(html: str, subject: str, mail_from: str, mail_to: str):
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # Split comma-separated list
    recipients = [x.strip() for x in mail_to.split(",") if x.strip()]

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)   # Proper header formatting

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)

            server.sendmail(mail_from, recipients, msg.as_string())
            logger.info(f"Email sent successfully to: {recipients}")

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check SMTP_USER/SMTP_PASS.")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while sending email: {e}")
