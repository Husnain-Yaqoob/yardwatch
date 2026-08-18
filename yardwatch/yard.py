"""Bay allocation and queue management.

Core invariant: the number of vehicles in ON_SITE state never exceeds
`capacity`. Everything else follows from that.

Admission is strictly first-come-first-served by arrival time. This is a
deliberate choice — see README, "Why FIFO". A priority scheme would reduce
mean wait but is unenforceable by a single operator at a barrier and invites
disputes with drivers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from .models import Vehicle, VehicleState


class YardFullError(RuntimeError):
    """Raised when admission is attempted with no free bay."""


class Yard:
    """Tracks occupancy of a fixed number of bays and the overflow queue."""

    def __init__(self, capacity: int = 2) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._vehicles: list[Vehicle] = []

    # ---------- state views ----------

    @property
    def on_site(self) -> list[Vehicle]:
        return [v for v in self._vehicles if v.state is VehicleState.ON_SITE]

    @property
    def queue(self) -> list[Vehicle]:
        """Vehicles waiting on the public road, oldest arrival first."""
        waiting = [v for v in self._vehicles if v.state is VehicleState.QUEUED]
        return sorted(waiting, key=lambda v: v.arrived_at)

    @property
    def departed(self) -> list[Vehicle]:
        return [v for v in self._vehicles if v.state is VehicleState.DEPARTED]

    @property
    def free_bays(self) -> list[int]:
        taken = {v.bay for v in self.on_site}
        return [b for b in range(1, self.capacity + 1) if b not in taken]

    @property
    def is_full(self) -> bool:
        return not self.free_bays

    # ---------- transitions ----------

    def arrive(self, reference: str, carrier: str, at: datetime) -> Vehicle:
        """Record a vehicle arriving at the barrier.

        The vehicle joins the queue regardless of capacity; admission is a
        separate decision so that queue time is always measured, even when a
        bay happens to be free and the wait is near zero.
        """
        vehicle = Vehicle(reference=reference, carrier=carrier, arrived_at=at)
        self._vehicles.append(vehicle)
        return vehicle

    def admit_next(self, at: datetime) -> Optional[Vehicle]:
        """Admit the longest-waiting vehicle, if a bay is free.

        Returns None when the queue is empty. Raises YardFullError when
        vehicles are waiting but no bay is available — the caller should check
        `is_full` first; the exception exists to make misuse loud rather than
        silently dropping a vehicle.
        """
        waiting = self.queue
        if not waiting:
            return None
        if self.is_full:
            raise YardFullError(
                f"all {self.capacity} bays occupied; {len(waiting)} vehicle(s) waiting"
            )

        vehicle = waiting[0]
        vehicle.state = VehicleState.ON_SITE
        vehicle.admitted_at = at
        vehicle.bay = self.free_bays[0]
        return vehicle

    def depart(self, reference: str, at: datetime) -> Vehicle:
        """Record a vehicle leaving the site, freeing its bay."""
        for vehicle in self.on_site:
            if vehicle.reference == reference:
                vehicle.state = VehicleState.DEPARTED
                vehicle.departed_at = at
                vehicle.bay = None
                return vehicle
        raise KeyError(f"no on-site vehicle with reference {reference!r}")

    def tick(self, at: datetime) -> list[Vehicle]:
        """Admit as many queued vehicles as there are free bays.

        This is what an operator does after a departure: check who is waiting
        and wave the next one through.
        """
        admitted = []
        while self.queue and not self.is_full:
            vehicle = self.admit_next(at)
            if vehicle is None:
                break
            admitted.append(vehicle)
        return admitted

    # ---------- history ----------

    def all_vehicles(self) -> list[Vehicle]:
        return list(self._vehicles)
