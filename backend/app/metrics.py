from __future__ import annotations

from .models import Metrics, Satellite, Task, TaskStatus


def collect_metrics(satellites: list[Satellite], tasks: list[Task], generated: float = 0, consumed: float = 0, components: int = 0) -> Metrics:
    return Metrics(
        completed_tasks=sum(t.status == TaskStatus.COMPLETE for t in tasks),
        failed_tasks=sum(t.status == TaskStatus.FAILED for t in tasks),
        energy_consumed_wh=consumed,
        energy_generated_wh=generated,
        average_temperature_c=sum(s.temperature_c for s in satellites) / max(1, len(satellites)),
        network_connected_components=components,
        allocations=sum(t.assigned_satellite is not None for t in tasks),
    )
