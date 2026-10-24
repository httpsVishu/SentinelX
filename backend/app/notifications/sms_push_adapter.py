"""SmsPushAdapter — sends urgent alerts via a generic SMS/push gateway
REST API (NOTIFICATION_MODE=sms_push).

The gateway's exact API shape varies by provider; this adapter assumes a
simple JSON POST interface (recipient + message) as a reasonable generic
default. Swap the request body/auth here for a specific provider's actual
API without touching alert_service.py or any other caller.
"""
import httpx

from app.config import settings
from app.notifications.base import NotificationAdapter, NotificationDeliveryError


class SmsPushAdapter(NotificationAdapter):
    name = "sms_push"

    def send(self, recipient_email: str, subject: str, message: str) -> None:
        if not settings.SMS_PUSH_PROVIDER_API_URL:
            raise NotificationDeliveryError(
                "NOTIFICATION_MODE=sms_push but SMS_PUSH_PROVIDER_API_URL is not configured."
            )

        try:
            resp = httpx.post(
                settings.SMS_PUSH_PROVIDER_API_URL,
                headers={"Authorization": f"Bearer {settings.SMS_PUSH_PROVIDER_API_KEY}"},
                json={"recipient": recipient_email, "subject": subject, "message": message},
                timeout=10,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise NotificationDeliveryError(f"SMS/push delivery failed: {exc}") from exc