"""Synthetic night-shift generator.

Every record this produces is fabricated. No real site data, vehicle
registration, carrier or personnel name is used anywhere in this project.

Arrivals are modelled as a Poisson process with an hourly rate that rises
after midnight, which is the pattern the two-bay constraint has to survive.
Dwell time is drawn from a log-normal distribution — most vehicles turn around
quickly, a few take much longer, and it is those long tails that cause the
queue to spill onto the road.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .models import Event, EventType, Severity, Shift
from .yard import Yard

CARRIERS = [
    "Northbound Haulage",
    "Coastal Freight",
    "Meridian Logistics",
    "Blackwater Transport",
    "Sixmile Distribution",
]

FAULTS = [
    ("Barrier arm slow to raise, intermittent", Severity.MEDIUM),
    ("Lock panel on gate 2 not engaging", Severity.HIGH),
    ("Floodlight out on north perimeter", Severity.LOW),
    ("Radio handset battery not holding charge", Severity.MEDIUM),
    ("CCTV feed 4 dropping out intermittently", Severity.HIGH),
]

# Arrivals are modelled as a *batch* (compound Poisson) process, not as
# independent arrivals.
#
# Why: observed volume is ~15 vehicles per night with a 20-45 min dwell, which
# is under 60% utilisation of two bays. Independent arrivals at that rate
# cannot produce the 7+ vehicle road queues actually seen — they would top out
# around 2 or 3. A queue that large at that volume only happens if vehicles
# turn up together, which matches reality: hauliers run to shared schedules and
# arrive in convoy.
#
# So HOURLY_RATE is the rate of arrival *events*, and each event brings a batch
# of vehicles drawn from BATCH_SIZES.
HOURLY_RATE = {22: 0.4, 23: 0.65, 0: 1.25, 1: 1.5, 2: 1.5, 3: 1.0, 4: 0.5, 5: 0.35}

# Vehicles per arrival event, and their relative likelihood. Most events are a
# single vehicle; the occasional convoy of four or five is what puts a long
# queue on the road.
BATCH_SIZES = [1, 2, 3, 4, 5]
BATCH_WEIGHTS = [0.44, 0.24, 0.16, 0.10, 0.06]

# Vehicles in a convoy arrive within a few minutes of each other, not
# simultaneously.
BATCH_SPREAD_MINUTES = 4


def _dwell_minutes(rng: random.Random) -> float:
    """Log-normal dwell: median ~30 min, most vehicles between 20 and 45.

    Log-normal rather than normal because turnaround cannot be negative and a
    few vehicles always take far longer than typical. Sigma is tuned so roughly
    two thirds of dwells fall in the observed 20-45 minute band.
    """
    return min(180.0, rng.lognormvariate(3.40, 0.35))


def run(
    operator: str = "Night Operator",
    start: datetime | None = None,
    hours: int = 8,
    capacity: int = 2,
    seed: int = 42,
) -> tuple[Shift, Yard]:
    """Simulate one night shift. Returns the shift log and the yard state."""
    rng = random.Random(seed)
    start = start or datetime(2026, 3, 14, 22, 0)

    yard = Yard(capacity=capacity)
    shift = Shift(operator=operator, started_at=start, ended_at=start + timedelta(hours=hours))

    # Build the arrival schedule first, as batches rather than single vehicles.
    arrivals: list[tuple[datetime, str, str]] = []
    counter = 0
    for offset in range(hours):
        moment = start + timedelta(hours=offset)
        rate = HOURLY_RATE.get(moment.hour, 1.0)
        for _ in range(_poisson(rng, rate)):
            batch_at = moment + timedelta(minutes=rng.randrange(60))
            batch_size = rng.choices(BATCH_SIZES, weights=BATCH_WEIGHTS, k=1)[0]
            # A convoy shares one carrier — they are running the same schedule.
            carrier = rng.choice(CARRIERS)
            for _ in range(batch_size):
                counter += 1
                arrivals.append(
                    (
                        batch_at + timedelta(minutes=rng.uniform(0, BATCH_SPREAD_MINUTES)),
                        f"V{counter:03d}",
                        carrier,
                    )
                )
    arrivals.sort(key=lambda item: item[0])

    # Replay arrivals and departures in timestamp order.
    departures: list[tuple[datetime, str]] = []
    pending = list(arrivals)
    end = start + timedelta(hours=hours)
    now = start

    while pending or departures:
        next_arrival = pending[0][0] if pending else None
        departures.sort()
        next_departure = departures[0][0] if departures else None

        candidates = [t for t in (next_arrival, next_departure) if t is not None]
        if not candidates:
            break
        now = min(candidates)
        if now > end:
            break

        if next_departure is not None and now == next_departure:
            _, reference = departures.pop(0)
            yard.depart(reference, now)
        else:
            moment, reference, carrier = pending.pop(0)
            yard.arrive(reference, carrier, moment)

        for vehicle in yard.tick(now):
            leaves = now + timedelta(minutes=_dwell_minutes(rng))
            departures.append((leaves, vehicle.reference))

    # Scatter a few events across the shift.
    for _ in range(rng.randint(2, 4)):
        description, severity = rng.choice(FAULTS)
        shift.events.append(
            Event(
                type=EventType.FAULT,
                description=description,
                occurred_at=start + timedelta(minutes=rng.randrange(hours * 60)),
                severity=severity,
                resolved=rng.random() < 0.4,
            )
        )

    for _ in range(hours):
        shift.events.append(
            Event(
                type=EventType.PATROL,
                description="Perimeter patrol completed, no issues found",
                occurred_at=start + timedelta(minutes=rng.randrange(hours * 60)),
            )
        )

    if rng.random() < 0.6:
        shift.events.append(
            Event(
                type=EventType.ACCESS_DENIED,
                description="Unauthorised vehicle turned away at barrier, no site access gained",
                occurred_at=start + timedelta(minutes=rng.randrange(hours * 60)),
                severity=Severity.MEDIUM,
            )
        )

    return shift, yard


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's Poisson sampler — random.Random has no poisson()."""
    import math

    target = math.exp(-lam)
    count, product = 0, 1.0
    while True:
        product *= rng.random()
        if product <= target:
            return count
        count += 1
