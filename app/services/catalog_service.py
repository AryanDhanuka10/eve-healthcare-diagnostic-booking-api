import logging
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.exceptions import ConflictError, NotFoundError
from app.models.centre_test import CentreTest
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.schemas.diagnostic import CentreCreate, CentreUpdate, TestCreate

logger = logging.getLogger(__name__)


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


# ---- centres -------------------------------------------------------------------------
def create_centre(db: Session, data: CentreCreate) -> DiagnosticCentre:
    centre = DiagnosticCentre(name=data.name, location=data.location)
    db.add(centre)
    _commit_or_conflict(db, "A centre with this name and location already exists", "CENTRE_EXISTS")
    logger.info("centre_created", extra={"event": "centre_created", "centre_id": str(centre.id)})
    return centre


def get_centre(db: Session, centre_id: uuid.UUID) -> DiagnosticCentre:
    centre = db.get(DiagnosticCentre, centre_id)
    if centre is None:
        raise NotFoundError("Centre not found", code="CENTRE_NOT_FOUND")
    return centre


def update_centre(db: Session, centre_id: uuid.UUID, data: CentreUpdate) -> DiagnosticCentre:
    centre = get_centre(db, centre_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(centre, field, value)
    _commit_or_conflict(db, "A centre with this name and location already exists", "CENTRE_EXISTS")
    return centre


def list_centres(db: Session, limit: int, offset: int) -> tuple[list[DiagnosticCentre], int]:
    rows = db.scalars(
        select(DiagnosticCentre)
        .order_by(DiagnosticCentre.name, DiagnosticCentre.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), _count(db, DiagnosticCentre)


# ---- tests ---------------------------------------------------------------------------
def create_test(db: Session, data: TestCreate) -> DiagnosticTest:
    test = DiagnosticTest(name=data.name, description=data.description)
    db.add(test)
    _commit_or_conflict(db, "A test with this name already exists", "TEST_EXISTS")
    return test


def get_test(db: Session, test_id: uuid.UUID) -> DiagnosticTest:
    test = db.get(DiagnosticTest, test_id)
    if test is None:
        raise NotFoundError("Test not found", code="TEST_NOT_FOUND")
    return test


def list_tests(db: Session, limit: int, offset: int) -> tuple[list[DiagnosticTest], int]:
    rows = db.scalars(
        select(DiagnosticTest).order_by(DiagnosticTest.name, DiagnosticTest.id).limit(limit).offset(offset)
    ).all()
    return list(rows), _count(db, DiagnosticTest)


# ---- offerings (centre <-> test with price) ------------------------------------------
def upsert_offering(db: Session, centre_id: uuid.UUID, test_id: uuid.UUID, price: Decimal) -> CentreTest:
    get_centre(db, centre_id)
    get_test(db, test_id)
    # Single-statement upsert: race-free, unlike "SELECT then INSERT or UPDATE".
    stmt = pg_insert(CentreTest).values(centre_id=centre_id, test_id=test_id, price=price)
    db.execute(
        stmt.on_conflict_do_update(
            index_elements=["centre_id", "test_id"], set_={"price": price, "updated_at": func.now()}
        )
    )
    db.commit()
    logger.info(
        "offering_upserted",
        extra={"event": "offering_upserted", "centre_id": str(centre_id), "test_id": str(test_id)},
    )
    return _load_offering(db, centre_id, test_id)


def _load_offering(db: Session, centre_id: uuid.UUID, test_id: uuid.UUID) -> CentreTest:
    return db.scalars(
        select(CentreTest)
        .where(CentreTest.centre_id == centre_id, CentreTest.test_id == test_id)
        .options(joinedload(CentreTest.test))
        .execution_options(populate_existing=True)
    ).one()


def list_offerings(
    db: Session, centre_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[CentreTest], int]:
    get_centre(db, centre_id)
    rows = db.scalars(
        select(CentreTest)
        .join(DiagnosticTest)
        .where(CentreTest.centre_id == centre_id)
        .options(joinedload(CentreTest.test))
        .order_by(DiagnosticTest.name, DiagnosticTest.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), _count(db, CentreTest, CentreTest.centre_id == centre_id)


def _commit_or_conflict(db: Session, message: str, code: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(message, code=code) from exc
