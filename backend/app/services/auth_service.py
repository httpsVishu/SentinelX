"""AuthService: login and token refresh.

Every failed login gets the same generic failure whether the email is unknown,
the password is wrong or the account is inactive (SRS: never reveal the reason
a login failed). Two details keep that true beyond the message text:

  - One bcrypt check always runs, against a placeholder hash when the email is
    unknown, so a missing account does not answer faster than a wrong password.
  - Throttling (rate_limit_service) treats known and unknown addresses alike.
"""
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.enums import AuditAction
from app.models.user import User
from app.services import audit_service, rate_limit_service


class AuthenticationError(Exception):
    """Generic authentication failure. The message is intentionally vague and
    the API layer must not add detail to the response."""


@lru_cache
def _dummy_hash() -> str:
    return hash_password("sentinelx-timing-placeholder")


def authenticate(db: Session, email: str, password: str, ip: str | None = None) -> tuple[str, str]:
    """Validate credentials and return (access_token, refresh_token).

    Raises RateLimitedError when too many recent attempts failed, and
    AuthenticationError for every other failure.
    """
    key = rate_limit_service.normalize_email(email)

    wait = rate_limit_service.seconds_until_allowed(db, key, ip)
    if wait > 0:
        raise rate_limit_service.RateLimitedError(wait)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    password_ok = verify_password(password, user.hashed_password if user is not None else _dummy_hash())
    valid = user is not None and user.is_active and password_ok

    if not valid:
        metadata = {"email": key}
        if ip:
            metadata["ip"] = ip
        audit_service.record(
            db,
            action=AuditAction.LOGIN_FAILURE,
            entity_type="user",
            entity_id=user.id if user else None,
            metadata=metadata,
        )
        db.commit()
        raise AuthenticationError("Invalid email or password.")

    user.last_login_at = datetime.now(timezone.utc)
    audit_service.record(
        db, action=AuditAction.LOGIN_SUCCESS, entity_type="user", entity_id=user.id,
        actor_id=user.id, metadata={"email": key},
    )
    db.commit()

    return create_access_token(user.id, user.role.value), create_refresh_token(user.id, user.role.value)


def refresh_access_token(db: Session, refresh_token: str) -> str:
    """Exchange a valid refresh token for a new access token."""
    try:
        payload = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired refresh token.") from exc

    user = db.execute(select(User).where(User.id == uuid.UUID(payload.sub))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired refresh token.")

    return create_access_token(user.id, user.role.value)