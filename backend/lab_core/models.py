"""Shared types. CPU is percentage points; energy Wh; data decimal MB; time s."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DOWNLINK = "downlink"
    COMPLETED = "completed"
    MISSED = "missed"


@dataclass
class Config:
    nodes: int = 6
    seed: int = 7
    dt_s: float = 2.0
    wall_interval_s: float = 0.5
    auto_tasks: bool = True
    arrival_interval_s: float = 24.0
    admm_iterations: int = 32
    admm_rho: float = 2.0
    admm_tolerance: float = 0.005
    pso_particles: int = 8
    pso_iterations: int = 12
    noise_scale: float = 1.0
    stale_after_s: float = 8.0
    candidate_limit: int = 24
    max_active_tasks: int = 96
    thermal_limit_c: float = 76.0
    reserve_wh: float = 12.0

    def __post_init__(self):
        bounds = {"nodes": (3,40), "seed": (0,2**31-1), "dt_s": (.25,5),
                  "wall_interval_s": (.1,5), "arrival_interval_s": (8,300),
                  "admm_iterations": (4,120), "admm_rho": (.1,20),
                  "admm_tolerance": (.00001,.1), "pso_particles": (4,16),
                  "pso_iterations": (1,20), "noise_scale": (0,5),
                  "stale_after_s": (4,60), "candidate_limit": (1,96),
                  "max_active_tasks": (2,500), "thermal_limit_c": (50,90),
                  "reserve_wh": (1,40)}
        integers = {"nodes", "seed", "admm_iterations", "pso_particles",
                    "pso_iterations", "candidate_limit", "max_active_tasks"}
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int,float))
                or not math.isfinite(value) or not low <= value <= high
                or (name in integers and not isinstance(value, int))):
                raise ValueError(f"Invalid {name}: expected {low}..{high}")


@dataclass
class Telemetry:
    time_s: float = 0.0
    battery_wh: float = 75.0
    temperature_c: float = 28.0
    cpu_pct: float = 15.0
    storage_mb: float = 0.0
    predicted_temperature_c: float = 28.0
    temperature_residual: float = 0.0


@dataclass
class Satellite:
    id: str
    index: int
    capabilities: tuple[str, ...] = ("gnss", "remote_sensing")
    battery_wh: float = 75.0
    battery_capacity_wh: float = 100.0
    temperature_c: float = 28.0
    cpu_capacity: float = 100.0
    control_cpu: float = 15.0
    allocated_cpu: float = 0.0
    actual_cpu: float = 15.0
    storage_capacity_mb: float = 256.0
    storage_used_mb: float = 0.0
    storage_reserved_mb: float = 0.0
    stress_cpu: float = 0.0
    extra_heat_w: float = 0.0
    extra_drain_w: float = 0.0
    cooling_scale: float = 1.0
    health: str = "healthy"
    reasons: list[str] = field(default_factory=list)
    faults: dict[str, float | None] = field(default_factory=dict)
    telemetry: Telemetry = field(default_factory=Telemetry)
    last_heartbeat_s: float = 0.0
    recovery_samples: int = 0
    tx_active: bool = False
    power_w: float = 0.0
    solar_w: float = 0.0

    @property
    def can_compute(self) -> bool:
        return self.health in ("healthy", "degraded") and "cpu" not in self.faults

    @property
    def can_relay(self) -> bool:
        return self.health in ("healthy", "degraded") and "radio" not in self.faults

    @property
    def free_cpu(self) -> float:
        return max(0.0, self.cpu_capacity - self.control_cpu - self.stress_cpu - self.allocated_cpu)

    @property
    def free_storage_mb(self) -> float:
        return max(0.0, self.storage_capacity_mb - self.storage_used_mb - self.storage_reserved_mb)


@dataclass
class Hop:
    source: str
    target: str
    start_s: float
    end_s: float
    rate_mbps: float
    weight: float


@dataclass
class Route:
    nodes: list[str]
    hops: list[Hop]
    arrival_s: float
    cost: float


@dataclass
class Link:
    source: str
    target: str
    start_s: float
    end_s: float
    rate_mbps: float
    latency_s: float
    loss: float
    weight: float

    @property
    def key(self) -> str:
        return "|".join(sorted((self.source, self.target)))


@dataclass
class Task:
    id: str
    kind: str
    region: str
    longitude_deg: float
    priority: int
    cpu_demand: float
    work_cpu_s: float
    output_mb: float
    created_s: float
    deadline_s: float
    campaign: str
    status: TaskStatus = TaskStatus.QUEUED
    owner: str | None = None
    holder: str | None = None
    progress_cpu_s: float = 0.0
    assigned_s: float | None = None
    completed_s: float | None = None
    attempts: int = 0
    reassignments: int = 0
    lost_work_cpu_s: float = 0.0
    route: Route | None = None
    receiver_reserved: str | None = None
    transfer_mb: float = 0.0
    note: str = "Waiting for resources"
    needs_repair: bool = False
    failure_time_s: float | None = None
    recovery_recorded: bool = False
    allowed_satellites: list[str] | None = None

    @property
    def remaining_cpu_s(self) -> float:
        return max(0.0, self.work_cpu_s - self.progress_cpu_s)

    @property
    def processing_s(self) -> float:
        return self.remaining_cpu_s / self.cpu_demand


@dataclass
class Event:
    time_s: float
    category: str
    message: str
    node_id: str | None = None
    task_id: str | None = None


@dataclass
class AllocationResult:
    fractions: dict[str, dict[str, float]] = field(default_factory=dict)
    costs: dict[str, dict[str, float]] = field(default_factory=dict)
    iterations: int = 0
    primal_residual: float = 0.0
    dual_residual: float = 0.0
    converged: bool = False
    runtime_ms: float = 0.0
    history: list[dict] = field(default_factory=list)
    local_constraint_violation: float = 0.0
    objective: float = 0.0
    message_scalars: int = 0


def serializable(value):
    """Dataclasses and string enums serialize directly with the standard JSON encoder."""
    return asdict(value)
