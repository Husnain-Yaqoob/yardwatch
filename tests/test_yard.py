from datetime import datetime, timedelta

import pytest

from yardwatch.models import VehicleState
from yardwatch.yard import Yard, YardFullError

T0 = datetime(2026, 3, 14, 22, 0)


def minutes(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


def test_capacity_is_never_exceeded():
    yard = Yard(capacity=2)
    for i in range(5):
        yard.arrive(f"V{i}", "Carrier", minutes(i))
    yard.tick(minutes(10))

    assert len(yard.on_site) == 2
    assert len(yard.queue) == 3


def test_admission_is_first_come_first_served():
    yard = Yard(capacity=1)
    yard.arrive("LATE", "Carrier", minutes(30))
    yard.arrive("EARLY", "Carrier", minutes(5))

    admitted = yard.admit_next(minutes(40))

    assert admitted is not None
    assert admitted.reference == "EARLY"


def test_departure_frees_a_bay_for_the_next_in_queue():
    yard = Yard(capacity=1)
    yard.arrive("FIRST", "Carrier", minutes(0))
    yard.arrive("SECOND", "Carrier", minutes(5))
    yard.tick(minutes(1))

    assert yard.is_full
    assert [v.reference for v in yard.queue] == ["SECOND"]

    yard.depart("FIRST", minutes(60))
    yard.tick(minutes(60))

    assert [v.reference for v in yard.on_site] == ["SECOND"]
    assert yard.queue == []


def test_admitting_into_a_full_yard_raises():
    yard = Yard(capacity=1)
    yard.arrive("FIRST", "Carrier", minutes(0))
    yard.arrive("SECOND", "Carrier", minutes(5))
    yard.tick(minutes(1))

    with pytest.raises(YardFullError):
        yard.admit_next(minutes(10))


def test_admit_next_returns_none_when_nobody_is_waiting():
    yard = Yard(capacity=2)
    assert yard.admit_next(minutes(0)) is None


def test_departing_an_unknown_vehicle_raises():
    yard = Yard(capacity=2)
    with pytest.raises(KeyError):
        yard.depart("GHOST", minutes(0))


def test_bay_numbers_are_reused_after_departure():
    yard = Yard(capacity=2)
    yard.arrive("A", "Carrier", minutes(0))
    yard.arrive("B", "Carrier", minutes(1))
    yard.tick(minutes(2))
    assert sorted(v.bay for v in yard.on_site) == [1, 2]

    yard.depart("A", minutes(30))
    yard.arrive("C", "Carrier", minutes(31))
    yard.tick(minutes(32))

    assert sorted(v.bay for v in yard.on_site) == [1, 2]


def test_wait_and_dwell_are_measured():
    yard = Yard(capacity=1)
    yard.arrive("A", "Carrier", minutes(0))
    yard.tick(minutes(20))
    yard.depart("A", minutes(50))

    vehicle = yard.all_vehicles()[0]
    assert vehicle.state is VehicleState.DEPARTED
    assert vehicle.wait_seconds == 20 * 60
    assert vehicle.dwell_seconds == 30 * 60


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        Yard(capacity=0)
