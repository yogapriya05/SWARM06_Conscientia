from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class SatelliteStatus(str, Enum):
    ACTIVE = "active"
    FAILED = "failed"
    ISOLATED = "isolated"


class TaskStatus(str, Enum):
    PENDING = "pending"
    ALLOCATED = "allocated"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass
class Satellite:
    id: str
    position: Tuple[float, float, float]
    battery_wh: float = 650.0
    battery_capacity_wh: float = 1000.0
    cpu_capacity: float = 100.0
    cpu_load: float = 0.0
    storage_capacity_gb: float = 64.0
    storage_used_gb: float = 0.0
    temperature_c: float = 20.0
    thermal_limit_c: float = 85.0
    solar_generation_w: float = 220.0
    status: SatelliteStatus = SatelliteStatus.ACTIVE
    eclipse: bool = False
    neighbors: List[str] = field(default_factory=list)
    swarm_id: str = "SWARM-01"
    orbital_phase: float = 0.0
    orbital_speed: float = 0.035

    @property
    def available_cpu(self) -> float:
        return max(0.0, self.cpu_capacity - self.cpu_load)

    @property
    def available_storage_gb(self) -> float:
        return max(0.0, self.storage_capacity_gb - self.storage_used_gb)

    @property
    def healthy(self) -> bool:
        return self.status == SatelliteStatus.ACTIVE and self.battery_wh > 0


@dataclass
class Task:
    id: str
    cpu_demand: float
    storage_demand_gb: float = 0.0
    energy_demand_wh: float = 1.0
    duration_s: float = 60.0
    priority: int = 1
    locked_satellite: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    assigned_satellite: Optional[str] = None
    name: Optional[str] = None
    kind: str = "compute"


@dataclass
class Allocation:
    task_id: str
    satellite_id: str
    score: float
    feasible: bool = True
    reason: str = ""


@dataclass
class FailureEvent:
    satellite_id: str
    reason: str
    isolated: bool = True
    timestamp: float = 0.0


@dataclass
class ContactGraph:
    edges: Dict[str, List[str]] = field(default_factory=dict)
    bandwidth_mbps: float = 100.0

    def neighbors(self, satellite_id: str) -> List[str]:
        return list(self.edges.get(satellite_id, []))


@dataclass
class Metrics:
    completed_tasks: int = 0
    failed_tasks: int = 0
    energy_consumed_wh: float = 0.0
    energy_generated_wh: float = 0.0
    average_temperature_c: float = 0.0
    network_connected_components: int = 0
    allocations: int = 0
