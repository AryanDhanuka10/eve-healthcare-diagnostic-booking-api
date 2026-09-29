import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.common import Name

Location = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class CentreCreate(BaseModel):
    name: Name
    location: Location


class CentreUpdate(BaseModel):
    name: Name | None = None
    location: Location | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "CentreUpdate":
        if self.name is None and self.location is None:
            raise ValueError("provide at least one of: name, location")
        return self


class CentreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    location: str
    created_at: datetime


class TestCreate(BaseModel):
    __test__ = False  # not a pytest class, despite the name

    name: Name
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


class TestRead(BaseModel):
    __test__ = False

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime


class OfferingUpsert(BaseModel):
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2, examples=["450.00"])


class OfferingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    centre_id: uuid.UUID
    test: TestRead
    price: Decimal
