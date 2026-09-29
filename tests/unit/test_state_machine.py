import itertools

import pytest

from app.exceptions import InvalidStateTransition
from app.models.enums import BookingStatus as B
from app.models.enums import PaymentStatus as P
from app.services.state_machine import (
    can_transition_booking,
    can_transition_payment,
    ensure_booking_transition,
    ensure_payment_transition,
)

VALID_BOOKING = {
    (B.PENDING, B.CONFIRMED),
    (B.PENDING, B.FAILED),
    (B.PENDING, B.CANCELLED),
    (B.CONFIRMED, B.CANCELLED),
}
VALID_PAYMENT = {(P.PENDING, P.SUCCESS), (P.PENDING, P.FAILED), (P.SUCCESS, P.REFUNDED)}


@pytest.mark.parametrize(("current", "target"), sorted(VALID_BOOKING))
def test_valid_booking_transitions(current, target):
    ensure_booking_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"), [p for p in itertools.product(B, B) if p not in VALID_BOOKING]
)
def test_every_other_booking_transition_is_rejected(current, target):
    assert not can_transition_booking(current, target)
    with pytest.raises(InvalidStateTransition) as exc:
        ensure_booking_transition(current, target)
    assert exc.value.status_code == 409


def test_named_illegal_booking_moves():
    for current, target in [(B.FAILED, B.CONFIRMED), (B.CANCELLED, B.CONFIRMED), (B.CONFIRMED, B.FAILED)]:
        with pytest.raises(InvalidStateTransition):
            ensure_booking_transition(current, target)


@pytest.mark.parametrize(("current", "target"), sorted(VALID_PAYMENT))
def test_valid_payment_transitions(current, target):
    ensure_payment_transition(current, target)


@pytest.mark.parametrize("pair", [p for p in itertools.product(P, P) if p not in VALID_PAYMENT])
def test_every_other_payment_transition_is_rejected(pair):
    assert not can_transition_payment(*pair)
    with pytest.raises(InvalidStateTransition):
        ensure_payment_transition(*pair)
