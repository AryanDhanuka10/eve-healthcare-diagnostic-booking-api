import uuid

from fastapi import APIRouter, status

from app.api.deps import AdminUser, DbSession, Page
from app.api.responses import errors
from app.schemas.common import Page as PageOut
from app.schemas.diagnostic import CentreCreate, CentreRead, CentreUpdate, OfferingRead, OfferingUpsert
from app.services import catalog_service

router = APIRouter(prefix="/centres", tags=["Centres"])


@router.get("", response_model=PageOut[CentreRead], summary="List diagnostic centres", responses=errors(422))
def list_centres(db: DbSession, page: Page):
    items, total = catalog_service.list_centres(db, page.limit, page.offset)
    return PageOut(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=CentreRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a centre (admin)",
    responses=errors(401, 403, 409, 422),
)
def create_centre(data: CentreCreate, db: DbSession, _: AdminUser):
    return catalog_service.create_centre(db, data)


@router.get("/{centre_id}", response_model=CentreRead, summary="Get a centre", responses=errors(404, 422))
def get_centre(centre_id: uuid.UUID, db: DbSession):
    return catalog_service.get_centre(db, centre_id)


@router.patch(
    "/{centre_id}",
    response_model=CentreRead,
    summary="Update a centre (admin)",
    responses=errors(401, 403, 404, 409, 422),
)
def update_centre(centre_id: uuid.UUID, data: CentreUpdate, db: DbSession, _: AdminUser):
    return catalog_service.update_centre(db, centre_id, data)


@router.get(
    "/{centre_id}/tests",
    response_model=PageOut[OfferingRead],
    summary="Tests offered by a centre, with prices",
    responses=errors(404, 422),
)
def list_centre_tests(centre_id: uuid.UUID, db: DbSession, page: Page):
    items, total = catalog_service.list_offerings(db, centre_id, page.limit, page.offset)
    return PageOut(items=items, total=total, limit=page.limit, offset=page.offset)


@router.put(
    "/{centre_id}/tests/{test_id}",
    response_model=OfferingRead,
    summary="Offer a test at a centre / change its price (admin)",
    responses=errors(401, 403, 404, 422),
)
def set_centre_test_price(
    centre_id: uuid.UUID, test_id: uuid.UUID, data: OfferingUpsert, db: DbSession, _: AdminUser
):
    """Idempotent upsert. Existing bookings keep the price they were created with."""
    return catalog_service.upsert_offering(db, centre_id, test_id, data.price)
