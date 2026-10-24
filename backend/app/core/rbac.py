"""Role-based access control dependencies and helpers.

FastAPI dependency factories that routers use to declare "this endpoint
requires role X" declaratively, plus a couple of ownership-check helpers
used by services to enforce that a Vendor can only ever touch their own
data — the SRS requirement that this be enforced in the backend, not only
hidden in the frontend.
"""
import uuid
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User


def require_role(*allowed_roles: UserRole) -> Callable[..., User]:
    """Dependency factory: require the current user to have one of the
    given roles. Usage: `current_user: User = Depends(require_role(UserRole.ADMIN))`.
    """

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _dependency


require_admin = require_role(UserRole.ADMIN)
require_vendor = require_role(UserRole.VENDOR)
require_any_role = require_role(UserRole.ADMIN, UserRole.VENDOR)


def assert_vendor_owns_resource(current_user: User, resource_vendor_id: uuid.UUID | None) -> None:
    """Raise 403 unless the current vendor user owns the resource being
    accessed. Admins are never subject to this check (callers should only
    invoke it inside vendor-scoped code paths).

    This is the backend enforcement point for "a Vendor shall never be able
    to see another vendor's tickets/scorecard/data" — every vendor-facing
    service function that fetches a Ticket, Scorecard, etc. must call this
    before returning data, not merely filter the query by convention.
    """
    if current_user.role != UserRole.VENDOR:
        return
    if current_user.vendor_id is None or current_user.vendor_id != resource_vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource.",
        )