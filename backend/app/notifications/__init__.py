"""Notification adapter factory — resolves the configured adapter based on
settings.NOTIFICATION_MODE, mirroring the pattern in app/scanners/__init__.py
and app/llm/__init__.py.
"""
from app.config import NotificationMode, settings
from app.notifications.base import NotificationAdapter
from app.notifications.dev_console_adapter import DevConsoleAdapter
from app.notifications.smtp_adapter import SmtpAdapter
from app.notifications.sms_push_adapter import SmsPushAdapter


def get_notification_adapter() -> NotificationAdapter:
    if settings.NOTIFICATION_MODE == NotificationMode.DEV_CONSOLE:
        return DevConsoleAdapter()
    if settings.NOTIFICATION_MODE == NotificationMode.SMTP:
        return SmtpAdapter()
    if settings.NOTIFICATION_MODE == NotificationMode.SMS_PUSH:
        return SmsPushAdapter()
    raise ValueError(f"Unknown notification mode: {settings.NOTIFICATION_MODE}")