"""Strict JSON API validation; invalid actions never partially mutate state."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SimulationConfig(StrictModel):
    nodes: int = Field(6, ge=3, le=40)
    seed: int = Field(7, ge=0, le=2**31 - 1)
    dt_s: float = Field(2, ge=.25, le=5)
    wall_interval_s: float = Field(.5, ge=.1, le=5)
    auto_tasks: bool = True
    arrival_interval_s: float = Field(24, ge=8, le=300)
    admm_iterations: int = Field(32, ge=4, le=120)
    admm_rho: float = Field(2, ge=.1, le=20)
    admm_tolerance: float = Field(.005, ge=.00001, le=.1)
    pso_particles: int = Field(8, ge=4, le=16)
    pso_iterations: int = Field(12, ge=1, le=20)
    noise_scale: float = Field(1, ge=0, le=5)
    stale_after_s: float = Field(8, ge=4, le=60)


class TaskRequest(StrictModel):
    kind: Literal["gnss", "remote_sensing"] = "gnss"
    region: str = Field("Bay of Bengal", min_length=1, max_length=80)
    longitude_deg: float = Field(88, ge=-180, le=180)
    priority: int = Field(5, ge=1, le=10)
    cpu_demand: float | None = Field(None, ge=5, le=75)
    processing_s: float | None = Field(None, ge=1, le=120)
    output_mb: float | None = Field(None, ge=.1, le=128)
    deadline_after_s: float = Field(180, ge=2, le=1800)
    allowed_satellites: list[str] | None = Field(None, min_length=1, max_length=40)


class FaultRequest(StrictModel):
    node_id: str = Field(pattern=r"^S[1-9][0-9]?$", max_length=3)
    kind: Literal["offline", "cpu", "radio", "thermal", "battery", "stale", "storage"] = "offline"
    duration_s: float | None = Field(None, ge=2, le=600)


class RecoveryRequest(StrictModel):
    node_id: str
    restore_resources: bool = True


class StressRequest(StrictModel):
    node_id: str
    cpu_pct: float = Field(0, ge=0, le=100)
    heat_w: float = Field(0, ge=0, le=120)
    drain_w: float = Field(0, ge=0, le=500)
    cooling_scale: float = Field(1, ge=.1, le=2)


class ControlRequest(StrictModel):
    action: Literal["run", "pause", "step"]
    ticks: int = Field(1, ge=1, le=200)


class LinkRequest(StrictModel):
    source: str
    target: str
    blocked: bool = True

    @model_validator(mode="after")
    def distinct(self):
        if self.source == self.target:
            raise ValueError("Link endpoints must differ")
        return self
