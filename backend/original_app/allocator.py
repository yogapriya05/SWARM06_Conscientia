from __future__ import annotations

from .models import Allocation, Satellite, Task, TaskStatus
from .resources import can_host, reserve


def allocation_score(satellite: Satellite, task: Task) -> float:
    # Higher battery and lower load are preferred, while keeping deterministic ties.
    return satellite.battery_wh / max(1.0, satellite.battery_capacity_wh) * 0.6 + (
        satellite.available_cpu / satellite.cpu_capacity
    ) * 0.4


def allocate(tasks: list[Task], satellites: list[Satellite], commit: bool = True) -> list[Allocation]:
    results: list[Allocation] = []
    for task in sorted(tasks, key=lambda x: (-x.priority, x.id)):
        candidates = [s for s in satellites if task.locked_satellite in (None, s.id)]
        feasible = [(allocation_score(s, task), s) for s in candidates if can_host(s, task)[0]]
        if not feasible:
            task.status = TaskStatus.FAILED
            results.append(Allocation(task.id, task.locked_satellite or "", 0, False, "no feasible satellite"))
            continue
        score, sat = max(feasible, key=lambda pair: (pair[0], pair[1].id))
        if commit:
            reserve(sat, task)
            task.assigned_satellite = sat.id
            task.status = type(task.status).ALLOCATED
        results.append(Allocation(task.id, sat.id, score))
    return results
