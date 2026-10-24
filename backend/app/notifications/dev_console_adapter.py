"""DevConsoleAdapter — logs alert deliveries to stdout instead of sending
real email/SMS.

The default adapter (NOTIFICATION_MODE=dev_console) so the full alert
pipeline — Alert row creation, delivery attempt, delivery_status update —
is exercised in local development and demos without any external service,
SMTP server, or SMS gateway required.
"""
import logging

from app.notifications.base import NotificationAdapter

logger = logging.getLogger("sentinelx.notifications.dev_console")


class DevConsoleAdapter(NotificationAdapter):
    name = "dev_console"

    def send(self, recipient_email: str, subject: str, message: str) -> None:
        logger.info(
            "DEV NOTIFICATION -> to=%s subject=%r message=%r",
            recipient_email, subject, message,
        )
        print(f"\n[DEV NOTIFICATION] To: {recipient_email}\nSubject: {subject}\n{message}\n")