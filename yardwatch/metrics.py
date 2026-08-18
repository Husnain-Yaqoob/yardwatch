"""Service-level indicators for the yard.

The operational question this answers is not "how many trucks came in" but
"how long were vehicles left waiting on a public road, and is two bays enough".

The headline SLI is `admitted_within_target` — the proportion of vehicles
admitted within the target wait. That framing is borrowed from service
reliability practice: pick a user-visible outcome, set a target, and measure
the proportion that meets it, rather than reporting an average that hides the
tail.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .models import Vehicle, VehicleState

# Target wait before admission. Vehicles queued longer than this are counted
# against the SLO.
DEFAULT_TARGET_WAIT = timedelta(minutes=15)


def percentile(values: list[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile. Returns None for an empty series.

    Deliberately not using numpy — the dependency is not worth it for this,
    and nearest-rank is unambiguous about which observation is reported.
    """
    if not values:
        return None
    if not 0 < pct <= 100:
        raise ValueError("pct must be in (0, 100]")
    ordered = sorted(values)
    # Ceiling, not round(): Python's round() uses banker's rounding, so
    # round(2.5) == 2 and the p50 of a 5-element series would come back as the
    # 2nd value instead of the 3rd.
    rank = max(1, math.ceil(pct / 100 * len(ordered)))
    return ordered[rank - 1]


@dataclass
class YardMetrics:
    """Computed indicators over a set of vehicle records."""

    total_arrivals: int
    total_admitted: int
    total_departed: int
    still_waiting: int

    wait_p50: Optional[float]
    wait_p90: Optional[float]
    wait_max: Optional[float]

    dwell_p50: Optional[float]
    dwell_p90: Optional[float]

    admitted_within_target: Optional[float]  # 0.0 - 1.0
    target_wait_seconds: float

    overflow_seconds: float  # total time at least one vehicle waited outside
    peak_queue_length: int
    busiest_hour: Optional[int]

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    def summary(self) -> str:
        def mins(seconds: Optional[float]) -> str:
            return "n/a" if seconds is None else f"{seconds / 60:.1f} min"

        slo = (
            "n/a"
            if self.admitted_within_target is None
            else f"{self.admitted_within_target * 100:.1f}%"
        )
        busiest = "n/a" if self.busiest_hour is None else f"{self.busiest_hour:02d}:00"

        return "\n".join(
            [
                f"Arrivals              {self.total_arrivals}",
                f"Admitted              {self.total_admitted}",
                f"Departed              {self.total_departed}",
                f"Still waiting         {self.still_waiting}",
                "",
                f"Wait  p50 / p90 / max {mins(self.wait_p50)} / {mins(self.wait_p90)} / {mins(self.wait_max)}",
                f"Dwell p50 / p90       {mins(self.dwell_p50)} / {mins(self.dwell_p90)}",
                "",
                f"SLO admitted <= {self.target_wait_seconds / 60:.0f} min   {slo}",
                f"Road overflow time    {mins(self.overflow_seconds)}",
                f"Peak queue length     {self.peak_queue_length}",
                f"Busiest arrival hour  {busiest}",
            ]
        )


def _overflow_and_peak(vehicles: Iterable[Vehicle]) -> tuple[float, int]:
    """Total seconds with a non-empty queue, and the longest the queue got.

    Built by replaying arrival and admission timestamps as a stream of +1/-1
    changes to queue length, rather than sampling — sampling would miss short
    spikes, which are exactly the events worth catching.
    """
    deltas: list[tuple[datetime, int]] = []
    for v in vehicles:
        deltas.append((v.arrived_at, +1))
        if v.admitted_at is not None:
            deltas.append((v.admitted_at, -1))

    if not deltas:
        return 0.0, 0

    deltas.sort(key=lambda pair: (pair[0], -pair[1]))

    overflow = 0.0
    peak = 0
    length = 0
    previous: Optional[datetime] = None

    for moment, change in deltas:
        if previous is not None and length > 0:
            overflow += (moment - previous).total_seconds()
        length += change
        peak = max(peak, length)
        previous = moment

    return overflow, peak


def compute(
    vehicles: Iterable[Vehicle],
    target_wait: timedelta = DEFAULT_TARGET_WAIT,
) -> YardMetrics:
    """Compute all indicators over the given vehicle records."""
    records = list(vehicles)

    admitted = [v for v in records if v.admitted_at is not None]
    departed = [v for v in records if v.state is VehicleState.DEPARTED]
    waiting = [v for v in records if v.state is VehicleState.QUEUED]

    waits = [v.wait_seconds for v in admitted if v.wait_seconds is not None]
    dwells = [v.dwell_seconds for v in departed if v.dwell_seconds is not None]

    target_seconds = target_wait.total_seconds()
    within = (
        sum(1 for w in waits if w <= target_seconds) / len(waits) if waits else None
    )

    overflow, peak = _overflow_and_peak(records)

    hours = Counter(v.arrived_at.hour for v in records)
    busiest = hours.most_common(1)[0][0] if hours else None

    return YardMetrics(
        total_arrivals=len(records),
        total_admitted=len(admitted),
        total_departed=len(departed),
        still_waiting=len(waiting),
        wait_p50=percentile(waits, 50),
        wait_p90=percentile(waits, 90),
        wait_max=max(waits) if waits else None,
        dwell_p50=percentile(dwells, 50),
        dwell_p90=percentile(dwells, 90),
        admitted_within_target=within,
        target_wait_seconds=target_seconds,
        overflow_seconds=overflow,
        peak_queue_length=peak,
        busiest_hour=busiest,
    )
