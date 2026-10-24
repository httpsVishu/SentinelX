"""Authentication endpoints: login and token refresh."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import AccessTokenResponse, LoginRequest, RefreshRequest, TokenResponse
from app.services.auth_service import AuthenticationError, authenticate, refresh_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        access_token, refresh_token = authenticate(db, data.email, data.password)
    except AuthenticationError as exc:
        # Generic 401 regardless of which part of the credential check
        # failed, per SRS: never reveal the specific reason a login
        # attempt failed.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenResponse:
    try:
        access_token = refresh_access_token(db, data.refresh_token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return AccessTokenResponse(access_token=access_token)