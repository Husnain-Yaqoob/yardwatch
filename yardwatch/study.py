"""Capacity sweeps across many simulated nights.

A single night proves nothing. Arrivals are bursty, so one night can be quiet
and the next gridlocked purely by chance — picking a seed that supports your
conclusion is how you end up with a confident wrong answer.

Everything here therefore reports across N independent nights: means for the
things you care about on average, and worst-case for the things that only have
to happen once to matter.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import timedelta

from . import metrics, simulate
from .metrics import DEFAULT_TARGET_WAIT


@dataclass
class CapacityResult:
    """Aggregated outcome for one bay count across many nights."""

    capacity: int
    nights: int
    mean_arrivals: float
    mean_slo: float           # 0.0 - 1.0, proportion admitted within target
    mean_overflow_minutes: float
    mean_peak_queue: float
    worst_peak_queue: int
    worst_wait_minutes: float
    nights_with_stranded: int  # nights where a vehicle never got in

    @property
    def stranded_rate(self) -> float:
        return self.nights_with_stranded / self.nights if self.nights else 0.0


def sweep(
    capacities: list[int],
    nights: int = 300,
    target_wait: timedelta = DEFAULT_TARGET_WAIT,
    hours: int = 8,
) -> list[CapacityResult]:
    """Run `nights` simulated shifts against each capacity.

    Each night uses seed `n` across every capacity, so the capacities are
    compared against the *same* set of nights rather than different random
    ones. Without that pairing, differences between capacities would be partly
    noise.
    """
    results = []

    for capacity in capacities:
        arrivals, slos, overflows, peaks, waits = [], [], [], [], []
        stranded = 0

        for night in range(nights):
            _, yard = simulate.run(capacity=capacity, seed=night, hours=hours)
            computed = metrics.compute(yard.all_vehicles(), target_wait=target_wait)

            arrivals.append(computed.total_arrivals)
            overflows.append(computed.overflow_seconds / 60)
            peaks.append(computed.peak_queue_length)
            if computed.admitted_within_target is not None:
                slos.append(computed.admitted_within_target)
            if computed.wait_max is not None:
                waits.append(computed.wait_max / 60)
            if computed.still_waiting:
                stranded += 1

        results.append(
            CapacityResult(
                capacity=capacity,
                nights=nights,
                mean_arrivals=statistics.mean(arrivals) if arrivals else 0.0,
                mean_slo=statistics.mean(slos) if slos else 0.0,
                mean_overflow_minutes=statistics.mean(overflows) if overflows else 0.0,
                mean_peak_queue=statistics.mean(peaks) if peaks else 0.0,
                worst_peak_queue=max(peaks) if peaks else 0,
                worst_wait_minutes=max(waits) if waits else 0.0,
                nights_with_stranded=stranded,
            )
        )

    return results


def as_markdown_table(results: list[CapacityResult]) -> str:
    """Render a sweep as a Markdown table, ready to paste into the README."""
    lines = [
        "| Bays | Admitted within target | Road overflow / night | Peak queue (mean) | Worst queue | Worst wait | Nights with stranded vehicles |",
        "|------|------------------------|-----------------------|-------------------|-------------|------------|-------------------------------|",
    ]
    for r in results:
        lines.append(
            f"| {r.capacity} "
            f"| {r.mean_slo * 100:.1f}% "
            f"| {r.mean_overflow_minutes:.0f} min "
            f"| {r.mean_peak_queue:.1f} "
            f"| {r.worst_peak_queue} "
            f"| {r.worst_wait_minutes:.0f} min "
            f"| {r.stranded_rate * 100:.0f}% |"
        )
    return "\n".join(lines)
