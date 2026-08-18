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

# Mean arrivals per hour across a 22:00-06:00 night shift. Tuned so that the
# two-bay constraint actually binds in the small hours — with a median dwell of
# ~35 min, two bays clear roughly 3.4 vehicles/hour, so rates above that are
# where the queue starts backing onto the road.
HOURLY_RATE = {22: 2.0, 23: 3.0, 0: 4.5, 1: 5.0, 2: 5.0, 3: 4.0, 4: 2.5, 5: 1.5}


def _dwell_minutes(rng: random.Random) -> float:
    """Log-normal dwell: median ~35 min, with a long tail."""
    return min(240.0, rng.lognormvariate(3.55, 0.55))


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

    # Build the arrival schedule first.
    arrivals: list[tuple[datetime, str, str]] = []
    counter = 0
    for offset in range(hours):
        moment = start + timedelta(hours=offset)
        rate = HOURLY_RATE.get(moment.hour, 1.5)
        for _ in range(_poisson(rng, rate)):
            counter += 1
            minute = rng.randrange(60)
            arrivals.append(
                (
                    moment + timedelta(minutes=minute),
                    f"V{counter:03d}",
                    rng.choice(CARRIERS),
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
