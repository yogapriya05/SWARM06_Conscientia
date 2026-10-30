from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .allocator import allocate
from .failures import apply_failure
from .metrics import collect_metrics
from .models import Satellite, Task
from .network import build_contact_graph
from .state import SwarmState


class SimulationEngine:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or self.load_config()
        sim, res, net = config.get("simulation", {}), config.get("resources", {}), config.get("network", {})
        count = int(sim.get("satellite_count", 6))
        self.timestep_seconds = float(sim.get("timestep_seconds", 60))
        self.orbit_period_seconds = float(sim.get("orbit_period_seconds", 5400))
        self.max_range_km = float(net.get("max_range_km", 2500))
        self.state = SwarmState([
            Satellite(
                f"SAT-{i+1:02d}", (i * 900.0, (i % 2) * 500.0, 500.0),
                battery_wh=float(res.get("initial_battery_wh", 650)),
                battery_capacity_wh=float(res.get("battery_capacity_wh", 1000)),
                solar_generation_w=float(res.get("solar_generation_w", 220)),
                thermal_limit_c=float(res.get("thermal_limit_c", 85)),
                cpu_capacity=float(res.get("cpu_capacity", 100)),
                storage_capacity_gb=float(res.get("storage_capacity_gb", 64)),
            ) for i in range(count)
        ])
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        self.generated_wh = self.consumed_wh = 0.0

    @staticmethod
    def load_config(path: str | Path = "config.yaml") -> dict[str, Any]:
        candidate = Path(path)
        if not candidate.exists():
            candidate = Path(__file__).resolve().parents[1] / "config.yaml"
        with candidate.open(encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def submit_tasks(self, tasks: list[Task]) -> list:
        self.state.tasks.extend(tasks)
        return allocate(tasks, self.state.satellites)

    def fail(self, satellite_id: str, reason: str = "manual failure"):
        event = apply_failure(self.state.satellites, self.state.tasks, satellite_id, reason, self.state.time_s)
        self.state.failures.append(event)
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        pending = [task for task in self.state.tasks if task.status.value == "pending"]
        if pending:
            allocate(pending, self.state.satellites)
        return event

    def step(self, seconds: float | None = None) -> dict:
        dt = float(seconds or self.timestep_seconds)
        for sat in self.state.satellites:
            eclipse = (self.state.time_s % self.orbit_period_seconds) > self.orbit_period_seconds / 2
            sat.eclipse = eclipse
            generation = 0 if eclipse else sat.solar_generation_w * dt / 3600
            discharge = sat.cpu_load * 0.01 * dt / 3600
            sat.battery_wh = min(sat.battery_capacity_wh, max(0.0, sat.battery_wh + generation - discharge))
            self.consumed_wh += discharge
            sat.cpu_load = max(0.0, sat.cpu_load - dt * 0.02)
            sat.temperature_c = max(20.0, sat.temperature_c - dt * 0.03)
            self.generated_wh += generation
        self.state.time_s += dt
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        self.state.metrics = collect_metrics(self.state.satellites, self.state.tasks, self.generated_wh, self.consumed_wh)
        return self.state.snapshot(self.graph)
