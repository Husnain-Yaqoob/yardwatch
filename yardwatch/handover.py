"""Shift handover report generation.

A handover fails when the incoming operator has to ask the outgoing one a
question that the log should already have answered. The report is therefore
ordered by what the next shift needs to act on — open faults first, vehicles
still on site second, everything else after.
"""

from __future__ import annotations

from datetime import datetime

from .models import EventType, Severity, Shift
from .metrics import YardMetrics
from .yard import Yard

_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


def _timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def _clock(moment: datetime) -> str:
    return moment.strftime("%H:%M")


def generate(shift: Shift, yard: Yard, metrics: YardMetrics) -> str:
    """Render a shift handover report as Markdown."""
    lines: list[str] = []

    lines.append(f"# Shift handover — {_timestamp(shift.started_at)}")
    lines.append("")
    lines.append(f"**Operator:** {shift.operator}")
    lines.append(f"**On:** {_timestamp(shift.started_at)}")
    lines.append(
        f"**Off:** {_timestamp(shift.ended_at) if shift.ended_at else 'still on shift'}"
    )
    if shift.duration_seconds is not None:
        lines.append(f"**Duration:** {shift.duration_seconds / 3600:.1f} h")
    lines.append("")

    # --- 1. what the next shift must act on ---
    open_faults = [e for e in shift.events if e.carries_over]
    lines.append("## Open faults carried over")
    lines.append("")
    if open_faults:
        for event in sorted(open_faults, key=lambda e: _SEVERITY_ORDER[e.severity]):
            lines.append(
                f"- **[{event.severity.value.upper()}]** {_clock(event.occurred_at)} — {event.description}"
            )
    else:
        lines.append("_None. No outstanding equipment faults._")
    lines.append("")

    # --- 2. current yard state ---
    lines.append("## Yard state at handover")
    lines.append("")
    lines.append(f"- Bays occupied: **{len(yard.on_site)} / {yard.capacity}**")
    lines.append(f"- Vehicles waiting outside: **{len(yard.queue)}**")
    lines.append("")

    if yard.on_site:
        lines.append("| Bay | Reference | Carrier | Admitted |")
        lines.append("|-----|-----------|---------|----------|")
        for vehicle in sorted(yard.on_site, key=lambda v: v.bay or 0):
            admitted = _clock(vehicle.admitted_at) if vehicle.admitted_at else "—"
            lines.append(
                f"| {vehicle.bay} | {vehicle.reference} | {vehicle.carrier} | {admitted} |"
            )
        lines.append("")

    if yard.queue:
        lines.append("Waiting on the road, in admission order:")
        lines.append("")
        for position, vehicle in enumerate(yard.queue, start=1):
            lines.append(
                f"{position}. {vehicle.reference} ({vehicle.carrier}) — arrived {_clock(vehicle.arrived_at)}"
            )
        lines.append("")

    # --- 3. shift summary ---
    lines.append("## Shift summary")
    lines.append("")
    lines.append("```")
    lines.append(metrics.summary())
    lines.append("```")
    lines.append("")

    # --- 4. full log ---
    other = [e for e in shift.events if not e.carries_over]
    lines.append("## Event log")
    lines.append("")
    if other:
        for event in sorted(other, key=lambda e: e.occurred_at):
            marker = "resolved" if event.type is EventType.FAULT else event.type.value
            lines.append(f"- {_clock(event.occurred_at)} `{marker}` — {event.description}")
    else:
        lines.append("_No further events logged._")
    lines.append("")

    return "\n".join(lines)
