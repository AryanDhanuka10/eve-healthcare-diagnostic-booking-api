import uuid

from fastapi import APIRouter, status

from app.api.deps import AdminUser, DbSession, Page
from app.api.responses import errors
from app.schemas.common import Page as PageOut
from app.schemas.diagnostic import TestCreate, TestRead
from app.services import catalog_service

router = APIRouter(prefix="/tests", tags=["Tests"])


@router.get("", response_model=PageOut[TestRead], summary="List diagnostic tests", responses=errors(422))
def list_tests(db: DbSession, page: Page):
    items, total = catalog_service.list_tests(db, page.limit, page.offset)
    return PageOut(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=TestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a test type (admin)",
    responses=errors(401, 403, 409, 422),
)
def create_test(data: TestCreate, db: DbSession, _: AdminUser):
    return catalog_service.create_test(db, data)


@router.get("/{test_id}", response_model=TestRead, summary="Get a test", responses=errors(404, 422))
def get_test(test_id: uuid.UUID, db: DbSession):
    return catalog_service.get_test(db, test_id)
