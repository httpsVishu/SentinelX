"""Pydantic schemas for authentication endpoints."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain strings, not EmailStr. A malformed address must fail the same way
    # as a wrong password (a generic 401), and reserved domains such as .local
    # used by the development seed accounts must still be able to sign in.
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"