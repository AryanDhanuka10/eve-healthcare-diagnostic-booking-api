import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.exceptions import AuthenticationError, PermissionDeniedError
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login", description="Log in via POST /auth/login (username = email)."
)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(db: DbSession, token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """Authentication: who is calling? Any failure is a 401."""
    subject = decode_access_token(token)
    try:
        user_id = uuid.UUID(subject)
    except ValueError as exc:
        raise AuthenticationError("Invalid token", code="INVALID_TOKEN") from exc
    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError("User no longer exists", code="INVALID_TOKEN")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """Authorization: is this caller allowed to do this? A failure is a 403."""
    if user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Admin privileges required", code="ADMIN_REQUIRED")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


@dataclass
class Pagination:
    limit: int
    offset: int


def pagination(
    limit: Annotated[int, Query(ge=1, le=100, description="Page size (1-100)")] = 20,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


Page = Annotated[Pagination, Depends(pagination)]
