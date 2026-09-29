from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    # Force UTC for every connection so timestamptz values always round-trip as UTC.
    connect_args={"options": "-c timezone=utc"},
)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. Services commit; anything uncommitted is rolled back."""
    with SessionLocal() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
