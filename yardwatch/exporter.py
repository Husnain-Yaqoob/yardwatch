"""Prometheus exporter — runs the yard as a live system.

The rest of the project analyses nights in batch. This runs one continuously in
accelerated time and exposes what an operator would actually want on a wall
display: how full the bays are, how many vehicles are on the road, and whether
waits are inside target.

Instrumentation follows the standard three metric types, chosen by what each
measures:

  Gauge     — a value that goes up and down (bays occupied, queue length)
  Counter   — a total that only increases (arrivals, admissions, SLO breaches)
  Histogram — a distribution (wait and dwell times), so Grafana can compute
              percentiles server-side with histogram_quantile()

Counters are never reset and never used for anything that can decrease; that
is what makes rate() meaningful.
"""

from __future__ import annotations

import argparse
import random
import time
from datetime import datetime, timedelta

from prometheus_client import Counter, Gauge, Histogram, start_http_server

from .metrics import DEFAULT_TARGET_WAIT
from .simulate import BATCH_SIZES, BATCH_SPREAD_MINUTES, BATCH_WEIGHTS, CARRIERS, HOURLY_RATE, _dwell_minutes
from .yard import Yard

# ---------------------------------------------------------------- metrics ---

BAYS_OCCUPIED = Gauge("yardwatch_bays_occupied", "Vehicles currently in a bay")
BAY_CAPACITY = Gauge("yardwatch_bay_capacity", "Total bays available")
QUEUE_LENGTH = Gauge(
    "yardwatch_queue_length", "Vehicles waiting on the public road outside the barrier"
)
SIM_HOUR = Gauge("yardwatch_simulated_hour", "Hour of day inside the simulation")
# Exported so dashboards can convert real-time rates into simulated-time rates
# without hard-coding the playback speed. rate() counts per real second; one
# real second covers (speedup / 60) simulated hours.
SPEEDUP = Gauge(
    "yardwatch_speedup_minutes_per_second",
    "Simulated minutes elapsed per real second",
)

ARRIVALS = Counter("yardwatch_arrivals_total", "Vehicles that have arrived", ["carrier"])
ADMISSIONS = Counter("yardwatch_admissions_total", "Vehicles admitted to a bay")
DEPARTURES = Counter("yardwatch_departures_total", "Vehicles that have left the site")
SLO_BREACHES = Counter(
    "yardwatch_slo_breaches_total",
    "Vehicles admitted later than the target wait",
)

# Buckets are chosen around the decision boundary rather than left at the
# library defaults: the 15-minute target must be an exact bucket edge, or the
# SLO computed in Grafana is an interpolation rather than a measurement.
WAIT_SECONDS = Histogram(
    "yardwatch_wait_seconds",
    "Time spent queued on the road before admission",
    buckets=(60, 300, 600, 900, 1800, 2700, 3600, 7200, float("inf")),
)
DWELL_SECONDS = Histogram(
    "yardwatch_dwell_seconds",
    "Time spent occupying a bay",
    buckets=(600, 1200, 1800, 2700, 3600, 5400, 7200, float("inf")),
)


# The simulation always advances one simulated minute per step, regardless of
# how fast wall-clock time is mapped onto it. Tying step size to the speed
# multiplier instead would mean fast mode steps the yard in hour-long jumps, so
# every vehicle appears to wait at least an hour — the measurement would be an
# artefact of the playback speed.
STEP_MINUTES = 1.0

# Daytime rate outside the modelled night-shift hours. Low enough that the yard
# drains during the day, which is what gives the dashboard a diurnal shape.
DAYTIME_RATE = 0.6


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's sampler — random.Random has no poisson()."""
    import math

    target = math.exp(-lam)
    count, product = 0, 1.0
    while True:
        product *= rng.random()
        if product <= target:
            return count
        count += 1


def run(
    capacity: int = 2,
    speedup: float = 60.0,
    seed: int | None = None,
    target_wait: timedelta = DEFAULT_TARGET_WAIT,
) -> None:
    """Step a live yard forever, updating metrics as events happen.

    `speedup` is simulated minutes per real second — at the default of 60, one
    simulated night passes in eight real minutes, so a Grafana dashboard shows
    a full traffic cycle while you watch it.
    """
    rng = random.Random(seed)
    yard = Yard(capacity=capacity)
    BAY_CAPACITY.set(capacity)
    SPEEDUP.set(speedup)

    clock = datetime(2026, 1, 1, 22, 0)
    departures: list[tuple[datetime, str]] = []
    scheduled: list[tuple[datetime, str, str]] = []
    next_hour_at = clock
    counter = 0
    target_seconds = target_wait.total_seconds()

    seconds_per_step = STEP_MINUTES / speedup

    while True:
        clock += timedelta(minutes=STEP_MINUTES)

        # --- schedule the next simulated hour of arrivals ---
        # Each batch gets its own random minute within the hour, matching
        # simulate.py. Dropping every batch at the same instant instead would
        # stack an entire hour of traffic into one spike and wildly overstate
        # the queue.
        if clock >= next_hour_at:
            rate = HOURLY_RATE.get(clock.hour, DAYTIME_RATE)
            for _ in range(_poisson(rng, rate)):
                batch_at = clock + timedelta(minutes=rng.uniform(0, 60))
                size = rng.choices(BATCH_SIZES, weights=BATCH_WEIGHTS, k=1)[0]
                carrier = rng.choice(CARRIERS)
                for _ in range(size):
                    counter += 1
                    scheduled.append(
                        (
                            batch_at + timedelta(minutes=rng.uniform(0, BATCH_SPREAD_MINUTES)),
                            f"V{counter:05d}",
                            carrier,
                        )
                    )
            next_hour_at = clock + timedelta(hours=1)

        # --- release vehicles whose arrival time has come ---
        scheduled.sort()
        while scheduled and scheduled[0][0] <= clock:
            arrives_at, reference, carrier = scheduled.pop(0)
            yard.arrive(reference, carrier, arrives_at)
            ARRIVALS.labels(carrier=carrier).inc()

        # --- departures that are now due ---
        departures.sort()
        while departures and departures[0][0] <= clock:
            _, reference = departures.pop(0)
            yard.depart(reference, clock)
            DEPARTURES.inc()

        # --- admit whoever fits ---
        for vehicle in yard.tick(clock):
            ADMISSIONS.inc()
            if vehicle.wait_seconds is not None:
                WAIT_SECONDS.observe(vehicle.wait_seconds)
                if vehicle.wait_seconds > target_seconds:
                    SLO_BREACHES.inc()
            dwell = _dwell_minutes(rng)
            DWELL_SECONDS.observe(dwell * 60)
            departures.append((clock + timedelta(minutes=dwell), vehicle.reference))

        BAYS_OCCUPIED.set(len(yard.on_site))
        QUEUE_LENGTH.set(len(yard.queue))
        SIM_HOUR.set(clock.hour + clock.minute / 60)

        time.sleep(seconds_per_step)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yardwatch.exporter",
        description="Expose a live simulated yard as Prometheus metrics.",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--capacity", type=int, default=2)
    parser.add_argument(
        "--speedup",
        type=float,
        default=60.0,
        help="simulated minutes per real second (default: 60)",
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--target-wait", type=int, default=15, help="minutes")
    args = parser.parse_args(argv)

    start_http_server(args.port)
    print(f"yardwatch exporter on :{args.port}/metrics  ({args.capacity} bays)")
    print("Ctrl+C to stop.")
    try:
        run(
            capacity=args.capacity,
            speedup=args.speedup,
            seed=args.seed,
            target_wait=timedelta(minutes=args.target_wait),
        )
    except KeyboardInterrupt:
        # Expected: this process is meant to be stopped by hand. Exit quietly
        # rather than dumping a traceback that looks like a crash.
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
