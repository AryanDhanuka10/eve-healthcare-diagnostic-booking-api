from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Trimmed, non-empty strings. Whitespace-only values fail min_length after stripping.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class Page[T](BaseModel):
    items: list[T]
    total: int = Field(description="Total rows matching the query, ignoring limit/offset")
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str = Field(examples=["NOT_FOUND"])
    message: str
    details: list[dict] | dict | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
