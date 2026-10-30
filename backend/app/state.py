from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import ContactGraph, Metrics, Satellite, SatelliteStatus, Task, TaskStatus


class SwarmState:
    def __init__(self, satellites: list[Satellite] | None = None, tasks: list[Task] | None = None):
        self.time_s = 0.0
        self.satellites = satellites or []
        self.tasks = tasks or []
        self.failures = []
        self.metrics = Metrics()

    def snapshot(self, graph: ContactGraph | None = None) -> dict[str, Any]:
        satellites = []
        for index, sat in enumerate(self.satellites):
            satellites.append({
                "id": sat.id,
                "name": sat.id,
                "swarm": sat.swarm_id,
                "x": min(0.94, max(0.06, (sat.position[0] % 6000) / 6000)),
                "y": min(0.88, max(0.08, (sat.position[1] % 4000) / 4000)),
                "status": "online" if sat.status == SatelliteStatus.ACTIVE else sat.status.value,
                "battery": sat.battery_wh / max(1, sat.battery_capacity_wh) * 100,
                "temperature": sat.temperature_c,
                "cpu_load": sat.cpu_load,
                "storage_used": sat.storage_used_gb / max(1, sat.storage_capacity_gb) * 100,
                "owner_task_ids": [t.id for t in self.tasks if t.assigned_satellite == sat.id],
                "solar_input_w": 0 if sat.eclipse else sat.solar_generation_w,
                "power_draw_w": sat.cpu_load,
            })
        tasks = [{
            "id": task.id,
            "name": task.name or task.id,
            "kind": task.kind,
            "priority": task.priority,
            "cpu_required": task.cpu_demand,
            "storage_required": task.storage_demand_gb,
            "power_required": task.energy_demand_wh,
            "duration_ticks": max(1, round(task.duration_s / 60)),
            "deadline_tick": int(self.time_s / 60 + task.duration_s / 60),
            "owner_id": task.assigned_satellite,
            "route": [task.assigned_satellite] if task.assigned_satellite else [],
            "status": task.status.value,
            "created_tick": 0,
        } for task in self.tasks]
        frontend_metrics = {
            "total_tasks": len(self.tasks),
            "completed_tasks": self.metrics.completed_tasks,
            "active_tasks": sum(t.status == TaskStatus.ALLOCATED for t in self.tasks),
            "failed_tasks": self.metrics.failed_tasks,
            "reassignment_count": len(self.failures),
            "recovery_count": len(self.failures),
            "average_recovery_ticks": 0.0,
            "network_availability": round(
                sum(s.status == SatelliteStatus.ACTIVE for s in self.satellites)
                / max(1, len(self.satellites)) * 100, 1
            ),
        }
        links = []
        if graph:
            for source, neighbors in graph.edges.items():
                for target in neighbors:
                    if source < target:
                        links.append({"source": source, "target": target, "distance_km": 0,
                                      "capacity_mbps": graph.bandwidth_mbps, "latency_ms": 1,
                                      "available": True})
        events = [{
            "id": f"failure-{index}",
            "tick": int(event.timestamp / 60),
            "kind": "NODE FAILURE",
            "message": f"{event.satellite_id} isolated: {event.reason}",
            "severity": "error",
            "satellite_id": event.satellite_id,
        } for index, event in enumerate(reversed(self.failures))]
        return {
            "time_s": self.time_s,
            "tick": int(self.time_s / 60),
            "running": True,
            "satellites": satellites,
            "tasks": tasks,
            "metrics": frontend_metrics,
            "links": links,
            "events": events,
        }
