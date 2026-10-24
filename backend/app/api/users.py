"""User endpoints: current-session profile, alert preferences, and
Admin-managed vendor accounts.

There is no public registration. Vendor logins are created by a Department
Admin for a vendor in their own department (Phase 1 assumption 3). Only the
vendor role can be created here, which keeps the two-role model intact.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rbac import require_admin, require_any_role
from app.core.security import hash_password
from app.database import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.user import UserCreate, UserRead, UserUpdatePreferences
from app.services import vendor_service

router = APIRouter(prefix="/users", tags=["users"])

MIN_PASSWORD_LENGTH = 8


@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(require_any_role)) -> User:
    return current_user


@router.patch("/me/preferences", response_model=UserRead)
def update_my_preferences(
    data: UserUpdatePreferences,
    current_user: User = Depends(require_any_role),
    db: Session = Depends(get_db),
) -> User:
    current_user.muted_trigger_types = data.muted_trigger_types
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/vendor/{vendor_id}", response_model=list[UserRead])
def list_vendor_users(
    vendor_id: uuid.UUID, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[User]:
    # get_vendor raises 404 when the vendor is not in the admin's department.
    vendor = vendor_service.get_vendor(db, vendor_id, current_user.department_id)
    stmt = select(User).where(User.vendor_id == vendor.id).order_by(User.full_name)
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=UserRead, status_code=201)
def create_vendor_user(
    data: UserCreate, current_user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> User:
    if data.role != UserRole.VENDOR or data.vendor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only vendor accounts can be created here. Choose the vendor this login belongs to.",
        )

    vendor = vendor_service.get_vendor(db, data.vendor_id, current_user.department_id)

    if len(data.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The password must be at least {MIN_PASSWORD_LENGTH} characters.",
        )

    already_used = db.execute(select(User.id).where(User.email == data.email)).scalar_one_or_none()
    if already_used is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(
        department_id=current_user.department_id,
        vendor_id=vendor.id,
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=UserRole.VENDOR,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user