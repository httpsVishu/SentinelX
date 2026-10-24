"""Shared FastAPI dependencies: database session and current-user resolution.

get_current_user is the single place a JWT access token is validated and
turned into a User row — every protected route depends on this (directly or
via app.core.rbac's require_* wrappers), so token validation logic never
needs to be duplicated in individual routers.
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except InvalidTokenError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    try:
        user_id = uuid.UUID(payload.sub)
    except ValueError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    if not user.is_active:
        # Deactivated account (SRS Use Case 4.3-1 A3) — deny access with a
        # specific-enough message here since the token itself was already
        # validated; this differs from the login-time generic-error rule,
        # which only applies to *credential* validation, not an
        # already-authenticated session hitting a deactivated account.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return user