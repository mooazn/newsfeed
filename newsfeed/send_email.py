import smtplib
from email.mime.text import MIMEText
import os

from .logging_setup import setup_logger

logger = setup_logger()


def send_via_gmail(html: str, subject: str, mail_from: str, mail_to: str):
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        logger.error("SMTP credentials missing: SMTP_USER / SMTP_PASS not set.")
        return

    msg = MIMEText(html, "html")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls()

            logger.info("Connecting to Gmail SMTP...")
            server.login(smtp_user, smtp_pass)

            server.send_message(msg)
            logger.info(f"Email sent successfully to {mail_to}")

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed — check SMTP_USER/SMTP_PASS.")
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending email: {e}")
    except Exception as e:
        logger.error(f"Unexpected error while sending email: {e}")
