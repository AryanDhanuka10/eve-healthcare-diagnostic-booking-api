import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import DUMMY_HASH, hash_password, verify_password
from app.exceptions import AuthenticationError, ConflictError
from app.models.user import User
from app.schemas.auth import SignupRequest

logger = logging.getLogger(__name__)


def signup(db: Session, data: SignupRequest) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise ConflictError("Email already registered", code="EMAIL_ALREADY_REGISTERED")
    user = User(email=data.email, hashed_password=hash_password(data.password), full_name=data.full_name)
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:  # two concurrent signups passed the pre-check
        db.rollback()
        raise ConflictError("Email already registered", code="EMAIL_ALREADY_REGISTERED") from exc
    logger.info("user_signed_up", extra={"event": "user_signed_up", "user_id": str(user.id)})
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    # Always run one hash verification so unknown-email and wrong-password look alike.
    valid = verify_password(password, user.hashed_password if user else DUMMY_HASH)
    if user is None or not valid:
        logger.warning("login_failed", extra={"event": "login_failed"})
        raise AuthenticationError("Incorrect email or password", code="INVALID_CREDENTIALS")
    return user
