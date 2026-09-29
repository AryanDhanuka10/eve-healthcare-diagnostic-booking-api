"""Single source of truth for booking and payment status transitions.

Every status change in the codebase goes through ensure_*_transition(), so an
illegal move (e.g. FAILED -> CONFIRMED) cannot be introduced by accident in a route.
"""

from app.exceptions import InvalidStateTransition
from app.models.enums import BookingStatus, PaymentStatus

BOOKING_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.PENDING: frozenset(
        {BookingStatus.CONFIRMED, BookingStatus.FAILED, BookingStatus.CANCELLED}
    ),
    BookingStatus.CONFIRMED: frozenset({BookingStatus.CANCELLED}),
    BookingStatus.FAILED: frozenset(),  # terminal: user must create a new booking
    BookingStatus.CANCELLED: frozenset(),  # terminal
}

PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.SUCCESS, PaymentStatus.FAILED}),
    PaymentStatus.SUCCESS: frozenset({PaymentStatus.REFUNDED}),  # cancelling a paid booking
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def can_transition_booking(current: BookingStatus, target: BookingStatus) -> bool:
    return target in BOOKING_TRANSITIONS[current]


def can_transition_payment(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in PAYMENT_TRANSITIONS[current]


def ensure_booking_transition(current: BookingStatus, target: BookingStatus) -> None:
    if not can_transition_booking(current, target):
        raise InvalidStateTransition("booking", current.value, target.value)


def ensure_payment_transition(current: PaymentStatus, target: PaymentStatus) -> None:
    if not can_transition_payment(current, target):
        raise InvalidStateTransition("payment", current.value, target.value)
