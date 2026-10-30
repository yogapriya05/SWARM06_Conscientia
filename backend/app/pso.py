from __future__ import annotations

from random import Random

from .allocator import allocate
from .models import Allocation, Satellite, Task
from .resources import can_host


def repair_allocation(
    tasks: list[Task],
    satellites: list[Satellite],
    locked_prefix: int = 0,
    iterations: int = 20,
    seed: int = 7,
) -> list[Allocation]:
    """Bounded local PSO-style repair; task assignments before locked_prefix are immutable."""
    locked = {task.id: task.assigned_satellite for task in tasks[:locked_prefix] if task.assigned_satellite}
    for task in tasks[locked_prefix:]:
        task.assigned_satellite = None
        task.status = type(task.status).PENDING
    best: list[Allocation] = []
    rng = Random(seed)
    for _ in range(max(1, iterations)):
        # A fresh deterministic candidate avoids mutating failed particle state.
        candidates = list(satellites)
        rng.shuffle(candidates)
        for task in tasks[:locked_prefix]:
            if task.assigned_satellite != locked.get(task.id):
                task.assigned_satellite = locked.get(task.id)
        candidate = allocate(tasks[locked_prefix:], candidates, commit=True)
        if not best or sum(a.feasible for a in candidate) > sum(a.feasible for a in best):
            best = candidate
        if all(a.feasible for a in candidate):
            break
    return [Allocation(t.id, locked[t.id], 1.0) for t in tasks[:locked_prefix] if t.id in locked] + best
