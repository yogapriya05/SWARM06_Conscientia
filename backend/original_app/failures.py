from __future__ import annotations

from .models import FailureEvent, Satellite, SatelliteStatus, Task, TaskStatus


def isolate_satellite(satellites: list[Satellite], satellite_id: str, reason: str = "manual failure", timestamp: float = 0) -> FailureEvent:
    for satellite in satellites:
        if satellite.id == satellite_id:
            satellite.status = SatelliteStatus.ISOLATED
            satellite.neighbors.clear()
            return FailureEvent(satellite_id, reason, True, timestamp)
    raise KeyError(satellite_id)


def apply_failure(satellites: list[Satellite], tasks: list[Task], satellite_id: str, reason: str = "failure", timestamp: float = 0) -> FailureEvent:
    event = isolate_satellite(satellites, satellite_id, reason, timestamp)
    for task in tasks:
        if task.assigned_satellite == satellite_id and task.status == TaskStatus.ALLOCATED:
            task.status = TaskStatus.PENDING
            task.assigned_satellite = None
    return event
