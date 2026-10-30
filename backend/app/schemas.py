from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    kind: str = "compute"
    cpu_demand: Optional[float] = Field(default=None, gt=0)
    cpu_required: Optional[float] = Field(default=None, gt=0)
    storage_demand_gb: float = Field(default=0, ge=0)
    storage_required: Optional[float] = Field(default=None, ge=0)
    energy_demand_wh: float = Field(default=1, ge=0)
    power_required: Optional[float] = Field(default=None, ge=0)
    duration_s: float = Field(default=60, gt=0)
    duration_ticks: Optional[int] = Field(default=None, gt=0)
    priority: int = 1
    locked_satellite: Optional[str] = None


class FailureRequest(BaseModel):
    satellite_id: Optional[str] = None
    swarm_id: Optional[str] = None
    failure_mode: str = "complete_outage"
    duration_ticks: int = Field(default=5, ge=1)
    reason: str = "manual failure"


class SwarmConfigRequest(BaseModel):
    swarm_count: int = Field(default=2, ge=1, le=8)
    satellites_per_swarm: int = Field(default=3, ge=1, le=12)


class StepRequest(BaseModel):
    seconds: Optional[float] = Field(default=None, gt=0)


class AllocationResponse(BaseModel):
    task_id: str
    satellite_id: str
    score: float
    feasible: bool
    reason: str = ""


class StateResponse(BaseModel):
    time_s: float
    satellites: list
    tasks: list
    metrics: dict
