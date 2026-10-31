"""One authoritative state for a single-process simulation; API access uses its lock."""
from __future__ import annotations

import random
from collections import deque
from dataclasses import asdict
from threading import RLock

from .models import AllocationResult, Config, Event, Satellite, Task, TaskStatus, Telemetry


class SimulationState:
    def __init__(self, config: Config | None = None):
        self.lock = RLock()
        self.config = config or Config()
        self.rng = random.Random(self.config.seed)
        self.time_s = 0.0
        self.tick = 0
        self.paused = True
        self.version = 0
        self.next_task = 1
        self.next_campaign = 1
        self.last_arrival_s = 0.0
        self.last_plan_tick = -100
        self.satellites: dict[str, Satellite] = {}
        for i in range(self.config.nodes):
            # All have GNSS-R receivers; one in four lacks the imaging payload.
            caps = ("gnss",) if i % 4 == 3 else ("gnss", "remote_sensing")
            sat = Satellite(id=f"S{i+1}", index=i, capabilities=caps,
                            battery_wh=72 + self.rng.uniform(-5, 9),
                            temperature_c=27 + self.rng.uniform(0, 5))
            sat.telemetry = Telemetry(battery_wh=sat.battery_wh,
                                      temperature_c=sat.temperature_c,
                                      predicted_temperature_c=sat.temperature_c)
            self.satellites[sat.id] = sat
        self.tasks: dict[str, Task] = {}
        self.events: deque[Event] = deque(maxlen=300)
        self.history: deque[dict] = deque(maxlen=240)
        self.allocator_result = AllocationResult()
        self.repair_stats: dict = {}
        self.blocked_links: set[str] = set()
        self.transfer_log: deque[dict] = deque(maxlen=500)
        self.recovery_delays_s: list[float] = []
        self.counters = dict(reassignments=0, reroutes=0, faults_detected=0,
                             recovered_nodes=0, dropped_mb=0.0, delivered_mb=0.0,
                             task_recovery_count=0, energy_used_wh=0.0)
        self.log("system", f"Swarm ready: {self.config.nodes} nodes. Simulation paused.")

    def log(self, category: str, message: str, node_id=None, task_id=None):
        self.events.append(Event(self.time_s, category, message, node_id, task_id))

    def active_tasks(self):
        return [t for t in self.tasks.values() if t.status not in
                (TaskStatus.COMPLETED, TaskStatus.MISSED)]

    def trim_tasks(self):
        # Bound long-running sessions while keeping cumulative terminal counters.
        terminal = [t for t in self.tasks.values() if t.status in
                    (TaskStatus.COMPLETED, TaskStatus.MISSED)]
        for t in terminal[:-400]:
            key = "archived_" + t.status.value
            self.counters[key] = self.counters.get(key, 0) + 1
            self.counters["archived_utility"] = self.counters.get("archived_utility", 0) + (
                t.priority if t.status == TaskStatus.COMPLETED else 0)
            self.tasks.pop(t.id)

    def snapshot(self):
        from .metrics import summarize
        nodes = []
        for sat in self.satellites.values():
            row = asdict(sat)
            row.update(free_cpu=sat.free_cpu, free_storage_mb=sat.free_storage_mb,
                       can_compute=sat.can_compute, can_relay=sat.can_relay,
                       telemetry_age_s=round(self.time_s - sat.telemetry.time_s, 3))
            nodes.append(row)
        return dict(version=self.version, time_s=self.time_s, tick=self.tick,
                    paused=self.paused, config=asdict(self.config), satellites=nodes,
                    tasks=[asdict(t) for t in self.tasks.values()],
                    events=[asdict(e) for e in list(self.events)[-80:]],
                    history=list(self.history), metrics=summarize(self),
                    allocator=asdict(self.allocator_result), repair=self.repair_stats)
