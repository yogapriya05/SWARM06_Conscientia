from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .allocator import allocate
from .failures import apply_failure
from .metrics import collect_metrics
from .models import Satellite, SatelliteStatus, Task
from .network import build_contact_graph
from .state import SwarmState


class SimulationEngine:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or self.load_config()
        sim, res, net = config.get("simulation", {}), config.get("resources", {}), config.get("network", {})
        self.swarm_count = int(sim.get("swarm_count", 2))
        self.satellites_per_swarm = int(sim.get("satellites_per_swarm", max(1, int(sim.get("satellite_count", 6)) // self.swarm_count)))
        count = self.swarm_count * self.satellites_per_swarm
        self.timestep_seconds = float(sim.get("timestep_seconds", 60))
        self.orbit_period_seconds = float(sim.get("orbit_period_seconds", 5400))
        self.max_range_km = float(net.get("max_range_km", 2500))
        self.state = SwarmState([
            Satellite(
                f"SAT-{swarm * self.satellites_per_swarm + member + 1:02d}",
                (1500.0 + swarm * 2200.0, member * 320.0, 500.0),
                battery_wh=float(res.get("initial_battery_wh", 650)),
                battery_capacity_wh=float(res.get("battery_capacity_wh", 1000)),
                solar_generation_w=float(res.get("solar_generation_w", 220)),
                thermal_limit_c=float(res.get("thermal_limit_c", 85)),
                cpu_capacity=float(res.get("cpu_capacity", 100)),
                storage_capacity_gb=float(res.get("storage_capacity_gb", 64)),
                swarm_id=f"SWARM-{swarm + 1:02d}",
                orbital_phase=(member / max(1, self.satellites_per_swarm)) * 6.28318 + swarm * 0.7,
                orbital_speed=0.035 + swarm * 0.004,
            )
            for swarm in range(self.swarm_count)
            for member in range(self.satellites_per_swarm)
        ])
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        self.generated_wh = self.consumed_wh = 0.0
        self.active_failures: dict[str, dict[str, Any]] = {}

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

    def fail_swarm(self, swarm_id: str, failure_mode: str, duration_ticks: int, reason: str = "manual swarm failure"):
        targets = [sat.id for sat in self.state.satellites if sat.swarm_id == swarm_id]
        if not targets:
            raise KeyError(swarm_id)
        for satellite_id in targets:
            self.fail(satellite_id, f"{failure_mode}: {reason}")
        self.active_failures[swarm_id] = {
            "mode": failure_mode,
            "remaining_ticks": duration_ticks,
            "satellite_ids": targets,
        }
        return self.state.snapshot(self.graph)

    def recover_swarm(self, swarm_id: str):
        failure = self.active_failures.pop(swarm_id, None)
        targets = failure["satellite_ids"] if failure else [
            sat.id for sat in self.state.satellites if sat.swarm_id == swarm_id
        ]
        for sat in self.state.satellites:
            if sat.id in targets:
                sat.status = SatelliteStatus.ACTIVE
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        pending = [task for task in self.state.tasks if task.status.value == "pending"]
        if pending:
            allocate(pending, self.state.satellites)
        return self.state.snapshot(self.graph)

    def step(self, seconds: float | None = None) -> dict:
        dt = float(seconds or self.timestep_seconds)
        for satellite in self.state.satellites:
            satellite.orbital_phase = (satellite.orbital_phase + satellite.orbital_speed * dt / 60.0) % 6.28318
            radius = 1450.0
            satellite.position = (
                3000.0 + radius * __import__("math").cos(satellite.orbital_phase),
                1700.0 + radius * __import__("math").sin(satellite.orbital_phase),
                satellite.position[2],
            )
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
        for swarm_id, failure in list(self.active_failures.items()):
            failure["remaining_ticks"] -= 1
            if failure["remaining_ticks"] <= 0:
                self.recover_swarm(swarm_id)
        self.graph = build_contact_graph(self.state.satellites, self.max_range_km)
        self.state.metrics = collect_metrics(self.state.satellites, self.state.tasks, self.generated_wh, self.consumed_wh)
        return self.state.snapshot(self.graph)
