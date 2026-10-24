"""SmtpAdapter — sends alert emails via a configured SMTP server
(NOTIFICATION_MODE=smtp).
"""
import smtplib
from email.mime.text import MIMEText

from app.config import settings
from app.notifications.base import NotificationAdapter, NotificationDeliveryError


class SmtpAdapter(NotificationAdapter):
    name = "smtp"

    def send(self, recipient_email: str, subject: str, message: str) -> None:
        if not settings.SMTP_HOST:
            raise NotificationDeliveryError(
                "NOTIFICATION_MODE=smtp but SMTP_HOST is not configured."
            )

        mime_message = MIMEText(message)
        mime_message["Subject"] = subject
        mime_message["From"] = settings.SMTP_FROM_ADDRESS
        mime_message["To"] = recipient_email

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
                if settings.SMTP_USE_TLS:
                    server.starttls()
                if settings.SMTP_USERNAME:
                    server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.sendmail(settings.SMTP_FROM_ADDRESS, [recipient_email], mime_message.as_string())
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationDeliveryError(f"SMTP delivery failed: {exc}") from exc