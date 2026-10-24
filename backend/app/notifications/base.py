"""NotificationAdapter — the interface every delivery channel implements.

Used exclusively by app/services/alert_service.py, which always writes the
Alert row before calling send() and catches any exception the adapter
raises, so a delivery failure here never loses the alert record itself.
"""
from abc import ABC, abstractmethod


class NotificationDeliveryError(Exception):
    """Raised when an adapter cannot deliver a message. Callers must catch
    this and mark the Alert's delivery_status as FAILED rather than letting
    it propagate and lose the alert."""


class NotificationAdapter(ABC):
    """Base interface for a single outbound notification channel."""

    name: str

    @abstractmethod
    def send(self, recipient_email: str, subject: str, message: str) -> None:
        """Deliver message to recipient_email. Raise
        NotificationDeliveryError on any failure. Implementations must not
        swallow failures silently — alert_service.py relies on the
        exception to mark delivery_status accurately."""
        raise NotImplementedError