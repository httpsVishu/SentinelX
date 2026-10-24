"""Password hashing and JWT issuing/verification.

Centralizes everything auth-related that touches cryptography so nothing
else in the codebase calls passlib/jose directly. Login failure messages
are intentionally generic everywhere this is used (see
app/services/auth_service.py) — SRS: "never reveal the specific reason a
login attempt failed."
"""
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    sub: str  # user id, as string
    role: str
    token_type: TokenType
    exp: datetime


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(user_id: uuid.UUID, role: str, token_type: TokenType, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {
        "sub": str(user_id),
        "role": role,
        "token_type": token_type.value,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    return _create_token(
        user_id, role, TokenType.ACCESS,
        timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: uuid.UUID, role: str) -> str:
    return _create_token(
        user_id, role, TokenType.REFRESH,
        timedelta(minutes=settings.JWT_REFRESH_TOKEN_EXPIRE_MINUTES),
    )


class InvalidTokenError(Exception):
    """Raised for any decode/validation failure. Callers should treat this
    uniformly as 401 Unauthorized without echoing the underlying reason."""


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    try:
        raw = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise InvalidTokenError("Token could not be decoded") from exc

    if raw.get("token_type") != expected_type.value:
        raise InvalidTokenError("Unexpected token type")

    try:
        return TokenPayload(**raw)
    except Exception as exc:  # noqa: BLE001 — any malformed payload is invalid
        raise InvalidTokenError("Malformed token payload") from exc