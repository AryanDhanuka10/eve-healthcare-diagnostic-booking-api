from sqlalchemy.exc import IntegrityError


def violated_constraint(exc: IntegrityError) -> str | None:
    """Name of the constraint/index PostgreSQL reports as violated (psycopg diag)."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
