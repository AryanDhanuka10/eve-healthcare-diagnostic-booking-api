from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.api.responses import errors
from app.core.security import create_access_token
from app.schemas.auth import SignupRequest, TokenResponse, UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses=errors(409, 422),
)
def signup(data: SignupRequest, db: DbSession):
    """Creates a normal (non-admin) user. Emails are case-insensitive and unique."""
    return auth_service.signup(db, data)


@router.post(
    "/login", response_model=TokenResponse, summary="Obtain a JWT access token", responses=errors(401, 422)
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    """OAuth2 password flow (form fields). Use the email as `username`."""
    user = auth_service.authenticate(db, form.username, form.password)
    token, expires_in = create_access_token(str(user.id))
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/me", response_model=UserRead, summary="Current user profile", responses=errors(401))
def me(user: CurrentUser):
    return user
