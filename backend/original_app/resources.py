from __future__ import annotations

from .models import Satellite, Task


def can_host(satellite: Satellite, task: Task) -> tuple[bool, str]:
    if not satellite.healthy:
        return False, "satellite unavailable"
    if satellite.available_cpu < task.cpu_demand:
        return False, "insufficient cpu"
    if satellite.available_storage_gb < task.storage_demand_gb:
        return False, "insufficient storage"
    if satellite.battery_wh < task.energy_demand_wh:
        return False, "insufficient battery"
    projected_temp = satellite.temperature_c + task.cpu_demand * 0.08
    if projected_temp > satellite.thermal_limit_c:
        return False, "thermal limit"
    return True, ""


def reserve(satellite: Satellite, task: Task) -> None:
    feasible, reason = can_host(satellite, task)
    if not feasible:
        raise ValueError(reason)
    satellite.cpu_load += task.cpu_demand
    satellite.storage_used_gb += task.storage_demand_gb
    satellite.battery_wh = max(0.0, satellite.battery_wh - task.energy_demand_wh)
    satellite.temperature_c += task.cpu_demand * 0.08
