"""Capability isolation using hard protection, timestamps and residual CUSUM."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Satellite


@dataclass
class CUSUM:
    k: float = .6
    h: float = 12.0
    value: float = 0.0

    def update(self, standardized_residual: float) -> bool:
        self.value = max(0.0, self.value + standardized_residual - self.k)
        return self.value >= self.h


class FailureMonitor:
    def __init__(self):
        self.detectors: dict[str, CUSUM] = {}
        self.last_sample: dict[str, float] = {}
        self.latched: set[str] = set()

    def reset_node(self, node: str):
        self.detectors.pop(node, None)
        self.last_sample.pop(node, None)
        self.latched.discard(node)

    def evaluate(self, sat: Satellite, state):
        c, now = state.config, state.time_s
        before = sat.health
        reasons = []
        full_isolation = False
        if "offline" in sat.faults:
            reasons.append("manual node shutdown")
            full_isolation = True
        if now - sat.telemetry.time_s > c.stale_after_s:
            reasons.append("sensor data stale")
            full_isolation = True
        if sat.temperature_c >= c.thermal_limit_c or "thermal" in sat.faults:
            reasons.append("thermal protection")
            full_isolation = True
        if sat.battery_wh <= c.reserve_wh or "battery" in sat.faults:
            reasons.append("battery reserve protection")
            full_isolation = True
        if sat.telemetry.time_s != self.last_sample.get(sat.id):
            sigma = max(.15, .15 * c.noise_scale)
            detector = self.detectors.setdefault(sat.id, CUSUM())
            # Known injected heater is hidden from the nominal thermal predictor.
            if detector.update(sat.telemetry.temperature_residual / sigma):
                self.latched.add(sat.id)
            self.last_sample[sat.id] = sat.telemetry.time_s
        if sat.id in self.latched:
            reasons.append("CUSUM: unexpected heating")
            full_isolation = True
        if "cpu" in sat.faults:
            reasons.append("processor disabled; relay remains available")
        if "radio" in sat.faults:
            reasons.append("radio disabled; local work may continue")
        if "storage" in sat.faults:
            reasons.append("storage fault")
            full_isolation = True
        target = "isolated" if full_isolation else "degraded" if reasons else "healthy"
        if target == "healthy" and before == "isolated":
            # Hysteresis: three fresh safe observations, not three replays.
            fresh = now == sat.telemetry.time_s
            safe = sat.temperature_c < c.thermal_limit_c - 6 and sat.battery_wh > c.reserve_wh + .5
            sat.recovery_samples = sat.recovery_samples + 1 if fresh and safe else 0
            if sat.recovery_samples < 3:
                target = "isolated"
                reasons = ["waiting for three fresh safe samples"]
        else:
            sat.recovery_samples = 0
        sat.health, sat.reasons = target, reasons
        if before != target:
            if target == "isolated" or target == "degraded":
                state.counters["faults_detected"] += 1
                state.log("fault", "; ".join(reasons), sat.id)
            elif target == "healthy":
                state.counters["recovered_nodes"] += 1
                state.log("recovery", "Node is healthy again", sat.id)


FAULT_KINDS = {"offline", "cpu", "radio", "thermal", "battery", "stale", "storage"}


def inject_fault(state, node: str, kind: str, duration_s: float | None = None):
    if node not in state.satellites or kind not in FAULT_KINDS:
        raise ValueError("Unknown node or fault kind")
    sat = state.satellites[node]
    sat.faults[kind] = state.time_s + duration_s if duration_s else None
    if kind == "thermal":
        sat.temperature_c = max(sat.temperature_c, state.config.thermal_limit_c + 5)
    if kind == "battery":
        sat.battery_wh = state.config.reserve_wh - 1
    state.log("injection", f"Injected {kind} fault" + (f" for {duration_s:g} s" if duration_s else ""), node)


def clear_faults(state, monitor: FailureMonitor, node: str, restore_resources=True):
    sat = state.satellites[node]
    sat.faults.clear()
    sat.stress_cpu = sat.extra_heat_w = sat.extra_drain_w = 0.0
    sat.cooling_scale = 1.0
    if restore_resources:
        sat.battery_wh = max(65, sat.battery_wh)
        sat.temperature_c = min(34, sat.temperature_c)
    monitor.reset_node(node)
    sat.recovery_samples = 0
    state.log("recovery", "Operator recovery: faults cleared and resources restored" if restore_resources
              else "Fault flags cleared; waiting for physical recovery", node)


def expire_faults(state, monitor):
    for sat in state.satellites.values():
        expired = [kind for kind, until in sat.faults.items() if until is not None and state.time_s >= until]
        for kind in expired:
            sat.faults.pop(kind)
            monitor.reset_node(sat.id)
            state.log("recovery", f"Transient {kind} fault ended", sat.id)
