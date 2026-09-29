"""Reusable OpenAPI `responses` blocks so every endpoint documents its error shapes."""

from typing import Any

from app.schemas.common import ErrorResponse

_DESCRIPTIONS = {
    400: "Bad request",
    401: "Missing, invalid or expired credentials",
    403: "Authenticated but not allowed",
    404: "Resource not found",
    409: "Conflict with current resource state",
    422: "Validation error or business-rule violation",
}


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {c: {"model": ErrorResponse, "description": _DESCRIPTIONS[c]} for c in codes}
