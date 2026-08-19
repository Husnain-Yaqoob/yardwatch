"""Tests for the exporter's instrumentation choices.

The run loop itself is infinite and not unit-tested — what is worth locking
down is the metric contract, since renaming a metric or changing a bucket
silently breaks every dashboard panel and alert built on it.
"""

import random

from prometheus_client import Counter, Gauge, Histogram

from yardwatch import exporter


def test_metric_types_match_what_they_measure():
    """Counters must not be used for values that can go down, or rate() lies."""
    assert isinstance(exporter.BAYS_OCCUPIED, Gauge)
    assert isinstance(exporter.QUEUE_LENGTH, Gauge)
    assert isinstance(exporter.BAY_CAPACITY, Gauge)

    assert isinstance(exporter.ADMISSIONS, Counter)
    assert isinstance(exporter.DEPARTURES, Counter)
    assert isinstance(exporter.SLO_BREACHES, Counter)
    assert isinstance(exporter.ARRIVALS, Counter)

    assert isinstance(exporter.WAIT_SECONDS, Histogram)
    assert isinstance(exporter.DWELL_SECONDS, Histogram)


def test_target_wait_is_an_exact_bucket_edge():
    """15 minutes must be a bucket boundary.

    If it is not, the SLO panel interpolates between buckets instead of
    reading a real count, and the headline number becomes an estimate.
    """
    buckets = exporter.WAIT_SECONDS._upper_bounds
    assert 900.0 in buckets, f"15 min missing from wait buckets: {buckets}"


def test_wait_buckets_are_ascending():
    buckets = exporter.WAIT_SECONDS._upper_bounds
    assert list(buckets) == sorted(buckets)


def test_step_size_is_independent_of_playback_speed():
    """Guards the bug where fast playback inflated every measured wait."""
    assert exporter.STEP_MINUTES == 1.0


def test_daytime_rate_lets_the_yard_drain():
    """Two bays clear roughly 3.4 vehicles/hour at the modelled dwell.

    The daytime arrival rate must sit below that or the queue grows without
    bound and the dashboard shows a runaway rather than a daily cycle.
    """
    from yardwatch.simulate import BATCH_SIZES, BATCH_WEIGHTS

    mean_batch = sum(s * w for s, w in zip(BATCH_SIZES, BATCH_WEIGHTS))
    vehicles_per_hour = exporter.DAYTIME_RATE * mean_batch
    assert vehicles_per_hour < 3.4, f"daytime rate {vehicles_per_hour:.2f}/hr will not drain"


def test_poisson_sampler_is_non_negative_and_roughly_right():
    rng = random.Random(0)
    draws = [exporter._poisson(rng, 2.0) for _ in range(4000)]
    assert all(d >= 0 for d in draws)
    assert 1.8 < sum(draws) / len(draws) < 2.2
