"""Resource dynamics, noisy sensors and an independent admission validator.

The lumped thermal model is an accelerated, illustrative approximation to
conduction and locally linearized radiative heat rejection, never convection.
"""
from __future__ import annotations

import math

from .models import Config, Satellite, Task, Telemetry

THERMAL_CAPACITY_J_K = 20.0
THERMAL_CONDUCTANCE_W_K = 0.9
REFERENCE_C = 20.0


def solar_power(sat: Satellite, time_s: float) -> float:
    # Accelerated synthetic sunlight/eclipse cycle, not orbital propagation.
    phase = (time_s + sat.index * 11) % 180
    return 46.0 if phase < 120 else 0.0


def thermal_step(temp: float, cpu: float, radio: bool, dt: float,
                 cooling=1.0, extra_heat=0.0) -> float:
    k = THERMAL_CONDUCTANCE_W_K * cooling
    heat = 4.0 + 0.50 * cpu + (5.0 if radio else 0.0) + extra_heat
    equilibrium = REFERENCE_C + heat / k
    return equilibrium + (temp - equilibrium) * math.exp(-k * dt / THERMAL_CAPACITY_J_K)


def resource_rows(sat: Satellite, tasks: list[Task], now: float, config: Config):
    """A x <= b, in normalized units, for a frozen admission problem.

    CPU/storage/energy are additive budgets. Thermal CPU headroom uses a
    conservative constant-load forecast at the longest candidate duration.
    Baseline energy is debited once for that common horizon; no solar credit.
    """
    import numpy as np
    horizon = min(240.0, max((t.processing_s for t in tasks), default=1.0) + 8.0)
    cpu = np.array([t.cpu_demand / 100.0 for t in tasks])
    storage = np.array([t.output_mb / sat.storage_capacity_mb for t in tasks])
    energy = np.array([task_energy_wh(t) / sat.battery_capacity_wh for t in tasks])
    measured_energy = min(sat.battery_wh, sat.telemetry.battery_wh - .12)
    baseline_w = 8 + .45 * (sat.control_cpu + sat.stress_cpu + sat.allocated_cpu) + sat.extra_drain_w
    available_wh = measured_energy - config.reserve_wh - baseline_w * horizon / 3600
    # Invert T(h) <= limit-margin for a constant CPU load, including existing jobs.
    k = THERMAL_CONDUCTANCE_W_K * sat.cooling_scale
    decay = math.exp(-k * horizon / THERMAL_CAPACITY_J_K)
    temp = max(sat.temperature_c, sat.telemetry.temperature_c + .6)
    max_heat = k * (config.thermal_limit_c - 2 - REFERENCE_C -
                    (temp - REFERENCE_C) * decay) / max(1e-9, 1 - decay)
    max_total_cpu = (max_heat - 9 - sat.extra_heat_w) / .50
    thermal_cpu = max(0.0, max_total_cpu - sat.control_cpu - sat.stress_cpu - sat.allocated_cpu)
    A = np.array([cpu, storage, energy, cpu])
    b = np.array([sat.free_cpu / 100.0, sat.free_storage_mb / sat.storage_capacity_mb,
                  max(0.0, available_wh) / sat.battery_capacity_wh, thermal_cpu / 100.0])
    return A, b


def task_energy_wh(task: Task) -> float:
    # Incremental processing + conservative per-product radio allowance.
    return .45 * task.remaining_cpu_s / 3600 + task.output_mb * .006


def visible(sat: Satellite, task: Task, now: float, nodes: int) -> bool:
    if task.kind == "gnss":
        return True
    angle = 360 * sat.index / nodes + .18 * now
    delta = math.radians((angle - task.longitude_deg + 180) % 360 - 180)
    return math.cos(delta) > -.25  # Synthetic broad footprint, not FOV geometry.


def can_host(sat: Satellite, task: Task, now: float, config: Config,
             check_visibility=True) -> tuple[bool, str]:
    if not sat.can_compute:
        return False, "processor unavailable"
    if now - sat.telemetry.time_s > config.stale_after_s:
        return False, "stale telemetry"
    if task.kind not in sat.capabilities:
        return False, "payload unavailable"
    if task.allowed_satellites and sat.id not in task.allowed_satellites:
        return False, "outside allowed host set"
    if check_visibility and not visible(sat, task, now, config.nodes):
        return False, "outside synthetic footprint"
    if now + task.processing_s >= task.deadline_s:
        return False, "processing deadline"
    A, b = resource_rows(sat, [task], now, config)
    labels = ("CPU budget", "storage budget", "battery reserve", "thermal forecast")
    for row, limit, label in zip(A, b, labels):
        if row[0] > limit + 1e-8:
            return False, label
    return True, "feasible"


def update_physics(sat: Satellite, dt: float, now: float, rng, config: Config):
    control = sat.control_cpu
    if "offline" in sat.faults:
        control = 3.0
    payload = 0.0 if not sat.can_compute else sat.allocated_cpu
    sat.actual_cpu = min(sat.cpu_capacity, control + sat.stress_cpu + payload)
    sat.power_w = 8 + .45 * sat.actual_cpu + (8 if sat.tx_active else 0) + sat.extra_drain_w
    sat.solar_w = solar_power(sat, now)
    energy_before = sat.battery_wh
    sat.battery_wh = min(sat.battery_capacity_wh, max(0.0,
        energy_before + (.9 * sat.solar_w - sat.power_w) * dt / 3600))
    predicted = thermal_step(sat.temperature_c, sat.actual_cpu, sat.tx_active, dt,
                             sat.cooling_scale)
    sat.temperature_c = thermal_step(sat.temperature_c, sat.actual_cpu, sat.tx_active,
                                    dt, sat.cooling_scale, sat.extra_heat_w)
    if "offline" not in sat.faults and "radio" not in sat.faults:
        sat.last_heartbeat_s = now
    if "offline" not in sat.faults and "stale" not in sat.faults:
        scale = config.noise_scale
        measured_temp = sat.temperature_c + rng.gauss(0, .15 * scale)
        sat.telemetry = Telemetry(time_s=now,
            battery_wh=min(100, max(0, sat.battery_wh + rng.gauss(0, .03 * scale))),
            temperature_c=measured_temp,
            cpu_pct=min(100, max(0, sat.actual_cpu + rng.gauss(0, .5 * scale))),
            storage_mb=max(0, sat.storage_used_mb + rng.gauss(0, .04 * scale)),
            predicted_temperature_c=predicted,
            temperature_residual=measured_temp - predicted)
    return sat.power_w * dt / 3600
