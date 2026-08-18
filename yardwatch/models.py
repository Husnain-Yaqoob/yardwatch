"""Domain model for a capacity-constrained vehicle yard.

The site has a fixed number of bays inside the perimeter barrier. When every
bay is occupied, arriving vehicles must wait on the public road outside — which
is the condition this system exists to measure and minimise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VehicleState(str, Enum):
    """Where a vehicle is in its journey through the yard."""

    QUEUED = "queued"      # waiting outside the barrier, on the public road
    ON_SITE = "on_site"    # admitted, occupying a bay
    DEPARTED = "departed"  # left the site


class EventType(str, Enum):
    """Things worth recording during a shift."""

    FAULT = "fault"              # equipment defect (barrier, lock panel, lighting)
    ACCESS_DENIED = "access_denied"  # unauthorised access attempt turned away
    PATROL = "patrol"            # completed perimeter patrol
    NOTE = "note"                # anything else the next shift should know


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Vehicle:
    """A third-party vehicle requesting access to the yard.

    `carrier` is a free-text label for the operating company. Never store
    driver names, and treat the vehicle reference as a site-local identifier
    rather than a real registration plate.
    """

    reference: str
    carrier: str
    arrived_at: datetime
    state: VehicleState = VehicleState.QUEUED
    admitted_at: Optional[datetime] = None
    departed_at: Optional[datetime] = None
    bay: Optional[int] = None
    id: Optional[int] = None

    @property
    def wait_seconds(self) -> Optional[float]:
        """Time spent queued on the public road before admission."""
        if self.admitted_at is None:
            return None
        return (self.admitted_at - self.arrived_at).total_seconds()

    @property
    def dwell_seconds(self) -> Optional[float]:
        """Time spent occupying a bay."""
        if self.admitted_at is None or self.departed_at is None:
            return None
        return (self.departed_at - self.admitted_at).total_seconds()


@dataclass
class Event:
    """A loggable occurrence during a shift."""

    type: EventType
    description: str
    occurred_at: datetime
    severity: Severity = Severity.LOW
    resolved: bool = False
    id: Optional[int] = None

    @property
    def carries_over(self) -> bool:
        """Unresolved faults must be handed to the next shift."""
        return self.type is EventType.FAULT and not self.resolved


@dataclass
class Shift:
    """One operator's shift. Mirrors the log-on / log-off record."""

    operator: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    events: list[Event] = field(default_factory=list)
    id: Optional[int] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()
