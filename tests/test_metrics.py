from datetime import datetime, timedelta

from yardwatch import metrics
from yardwatch.yard import Yard

T0 = datetime(2026, 3, 14, 22, 0)


def minutes(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


def test_percentile_handles_empty_series():
    assert metrics.percentile([], 50) is None


def test_percentile_nearest_rank():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert metrics.percentile(values, 50) == 3.0
    assert metrics.percentile(values, 100) == 5.0


def test_slo_counts_only_vehicles_within_target():
    yard = Yard(capacity=1)
    yard.arrive("FAST", "Carrier", minutes(0))
    yard.tick(minutes(5))          # 5 min wait — inside a 15 min target
    yard.depart("FAST", minutes(10))

    yard.arrive("SLOW", "Carrier", minutes(10))
    yard.tick(minutes(40))         # 30 min wait — breaches

    computed = metrics.compute(yard.all_vehicles(), target_wait=timedelta(minutes=15))

    assert computed.total_admitted == 2
    assert computed.admitted_within_target == 0.5


def test_overflow_time_is_zero_when_nobody_ever_waits():
    yard = Yard(capacity=2)
    yard.arrive("A", "Carrier", minutes(0))
    yard.tick(minutes(0))          # admitted instantly

    computed = metrics.compute(yard.all_vehicles())

    assert computed.overflow_seconds == 0
    assert computed.peak_queue_length == 1


def test_overflow_time_accumulates_while_a_queue_exists():
    yard = Yard(capacity=1)
    yard.arrive("A", "Carrier", minutes(0))
    yard.tick(minutes(0))
    yard.arrive("B", "Carrier", minutes(10))   # queues from here
    yard.depart("A", minutes(40))
    yard.tick(minutes(40))                      # admitted at 40

    computed = metrics.compute(yard.all_vehicles())

    assert computed.overflow_seconds == 30 * 60
    assert computed.peak_queue_length == 1


def test_still_waiting_vehicles_are_counted():
    yard = Yard(capacity=1)
    yard.arrive("A", "Carrier", minutes(0))
    yard.arrive("B", "Carrier", minutes(1))
    yard.tick(minutes(2))

    computed = metrics.compute(yard.all_vehicles())

    assert computed.still_waiting == 1
    assert computed.total_admitted == 1


def test_busiest_hour_is_reported():
    yard = Yard(capacity=2)
    yard.arrive("A", "Carrier", datetime(2026, 3, 15, 1, 10))
    yard.arrive("B", "Carrier", datetime(2026, 3, 15, 1, 40))
    yard.arrive("C", "Carrier", datetime(2026, 3, 15, 3, 5))

    computed = metrics.compute(yard.all_vehicles())

    assert computed.busiest_hour == 1


def test_empty_input_does_not_crash():
    computed = metrics.compute([])
    assert computed.total_arrivals == 0
    assert computed.wait_p50 is None
    assert computed.admitted_within_target is None
    assert "Arrivals" in computed.summary()
