"""Units: seconds, km, Wh, watts, decimal MB, cycles; JSON values stay finite."""
from dataclasses import dataclass, field
from collections import deque
import math

TERMINAL = {'delivered', 'expired', 'failed'}

@dataclass
class Config:
    swarm_count: int = 2
    satellites_per_swarm: int = 6
    seed: int = 7
    speed: float = 1.0
    auto_tasks: bool = True
    space_effects: bool = False
    random_revival: bool = True
    exaggerated_effects: bool = True
    reserve_wh: float = 12.0
    thermal_limit_c: float = 76.0
    stale_after_s: float = 8.0
    pso_iterations: int = 12
    pso_particles: int = 6
    max_active_tasks: int = 80
    def __post_init__(self):
        if self.swarm_count not in (1, 2) or not isinstance(self.swarm_count, int):
            raise ValueError('Use 1 or 2 swarms')
        if not isinstance(self.satellites_per_swarm, int) or not 1 <= self.satellites_per_swarm <= 20:
            raise ValueError('Use 1..20 satellites per swarm')
        if not math.isfinite(self.speed) or not 1 <= self.speed <= 100:
            raise ValueError('Speed must be 1..100')

@dataclass
class Satellite:
    id: str
    index: int
    swarm: str
    slot: int
    battery_wh: float = 78.0
    battery_capacity_wh: float = 100.0
    temperature_c: float = 29.0
    cpu_capacity: float = 100.0
    control_cpu: float = 10.0
    allocated_cpu: float = 0.0
    actual_cpu: float = 10.0
    cycles_per_s: float = 2_000_000
    storage_capacity_mb: float = 512.0
    storage_used_mb: float = 0.0
    storage_reserved_mb: float = 0.0
    stress_cpu: float = 0.0
    extra_heat_w: float = 0.0
    extra_drain_w: float = 0.0
    cooling_scale: float = 1.0
    health: str = 'healthy'
    faults: dict = field(default_factory=dict)
    reasons: list = field(default_factory=list)
    last_telemetry_s: float = 0.0
    recovery_samples: int = 0
    position: list = field(default_factory=lambda:[0.0, 0.0, 0.0])
    velocity: list = field(default_factory=lambda:[0.0, 0.0, 0.0])
    eclipse: bool = False
    solar_w: float = 40.0
    power_w: float = 12.0
    attitude_error_deg: float = 0.0
    antenna_error_deg: float = 0.0
    telemetry_residual_c: float = 0.0
    revival_at_s: float | None = None
    @property
    def can_compute(self):
        return self.health != 'isolated' and 'cpu' not in self.faults
    @property
    def can_relay(self):
        return self.health != 'isolated' and not {'radio','antenna'} & self.faults.keys()
    @property
    def can_observe(self):
        return self.can_compute and 'attitude' not in self.faults
    @property
    def free_cpu(self):
        return max(0., 100-self.control_cpu-self.stress_cpu-self.allocated_cpu)
    @property
    def free_storage_mb(self):
        return max(0., self.storage_capacity_mb-self.storage_used_mb-self.storage_reserved_mb)

@dataclass
class Task:
    task_id: str
    event_id: str
    target: dict
    created_at: float
    observation_window: list
    delivery_deadline: float
    priority: int = 3
    capture_duration_s: float = 5.0
    processing_cycles: float = 8_000_000
    raw_data_mb: float = 40.0
    output_data_mb: float = 10.0
    minimum_quality: float = .8
    required_captures: int = 1
    status: str = 'pending'
    owner: str | None = None
    holder: str | None = None
    name: str = 'Fire observation'
    kind: str = 'remote_sensing'
    progress_capture_s: float = 0.0
    progress_cycles: float = 0.0
    captures: int = 0
    quality: float = 0.0
    assigned_at: float | None = None
    captured_at: float | None = None
    processed_at: float | None = None
    delivered_at: float | None = None
    cpu_demand: float = 35.0
    route: list = field(default_factory=list)
    route_hops: list = field(default_factory=list)
    hop_index: int = 0
    receiver: str | None = None
    acked_packets: set = field(default_factory=set)
    pending_packets: list = field(default_factory=list)
    packet_attempts: dict = field(default_factory=dict)
    transfer_progress_mb: float = 0.0
    packet_count: int = 0
    valid_product: bool = False
    product_hash: str | None = None
    attempts: int = 0
    reassignments: int = 0
    note: str = 'Waiting for complete-chain feasibility'
    needs_repair: bool = False
    transitions: list = field(default_factory=list)
    visibility_windows: dict = field(default_factory=dict)
    allowed_satellites: list | None = None
    failure_at: float | None = None
    lease_version: int = 0
    lease_until_s: float = 0.0

@dataclass
class Link:
    source: str
    target: str
    weight: float
    rate_mbps: float
    latency_s: float
    distance_km: float
    doppler_hz: float
    available: bool
    physical_los: bool
    reason: str = ''
    loss: float = 0.0
    @property
    def key(self): return '|'.join(sorted((self.source, self.target)))
