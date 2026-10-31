"""Delivered products, resource usage, optimizer diagnostics and recovery latency."""
from __future__ import annotations

from statistics import mean

from .models import TaskStatus


def summarize(state):
    tasks = list(state.tasks.values())
    counts = {s.value: sum(t.status == s for t in tasks) for s in TaskStatus}
    counts["completed"] += state.counters.get("archived_completed", 0)
    counts["missed"] += state.counters.get("archived_missed", 0)
    total = sum(counts.values())
    delivered = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    campaigns = {t.campaign for t in tasks}
    paired = sum(all(t.status == TaskStatus.COMPLETED for t in tasks if t.campaign == cid)
                 and len({t.kind for t in tasks if t.campaign == cid}) == 2 for cid in campaigns)
    return dict(**counts, total_tasks=total,
        completion_pct=100 * counts["completed"] / max(1, total),
        delivered_utility=sum(t.priority for t in delivered) + state.counters.get("archived_utility", 0),
        mean_delivery_s=mean([t.completed_s - t.created_s for t in delivered]) if delivered else 0.0,
        paired_campaigns=paired,
        healthy_nodes=sum(s.health == "healthy" for s in state.satellites.values()),
        relay_nodes=sum(s.can_relay for s in state.satellites.values()),
        mean_battery_pct=mean(s.battery_wh for s in state.satellites.values()),
        max_temperature_c=max(s.temperature_c for s in state.satellites.values()),
        recovery_mean_s=mean(state.recovery_delays_s) if state.recovery_delays_s else None,
        **state.counters)
