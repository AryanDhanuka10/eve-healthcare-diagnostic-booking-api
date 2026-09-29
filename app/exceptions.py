"""Domain exceptions. Each maps to one HTTP status + a stable machine-readable code."""

from typing import Any


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class AuthenticationError(AppError):
    status_code = 401
    code = "AUTHENTICATION_FAILED"


class InvalidWebhookSignature(AuthenticationError):
    code = "INVALID_WEBHOOK_SIGNATURE"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "FORBIDDEN"


class BusinessRuleError(AppError):
    """Request is well-formed but violates a business rule (HTTP 422)."""

    status_code = 422
    code = "BUSINESS_RULE_VIOLATION"


class InvalidStateTransition(ConflictError):
    code = "INVALID_STATE_TRANSITION"

    def __init__(self, entity: str, current: str, target: str):
        super().__init__(f"Cannot move {entity} from {current} to {target}")
