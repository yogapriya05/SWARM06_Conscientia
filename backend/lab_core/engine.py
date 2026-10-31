"""Workflow: admit -> process/acquire -> buffer -> store-and-forward -> delivered."""
from __future__ import annotations

import math

from .allocator import allocate, rank_hosts
from .failures import FailureMonitor, clear_faults, expire_faults, inject_fault
from .metrics import summarize
from .models import Config, Task, TaskStatus
from .network import (GROUND, active_links, earliest_route, live_graph, pair_key,
                      route_candidates, tick_budgets)
from .pso import choose_repair_route, repair_placements
from .resources import can_host, update_physics
from .state import SimulationState

REGIONS = [("Bay of Bengal", 88), ("Arabian Sea", 68), ("Ganges delta", 91),
           ("Western coast", 73), ("Indian Ocean", 55)]


class Engine:
    def __init__(self, config: Config | None = None, seed_tasks=True):
        self.state = SimulationState(config)
        self.monitor = FailureMonitor()
        if seed_tasks:
            self.add_campaign()
            self.add_campaign()

    def reset(self, config: Config | None = None):
        # The API holds a service lock across reset; never replace a held state lock.
        self.__init__(config or self.state.config)

    def add_task(self, kind="gnss", region="Bay of Bengal", longitude_deg=88,
                 priority=5, cpu_demand=None, processing_s=None, output_mb=None,
                 deadline_after_s=180, campaign=None, allowed_satellites=None):
        s = self.state
        if len(s.active_tasks()) >= s.config.max_active_tasks:
            raise ValueError("Active task queue is full")
        if kind not in ("gnss", "remote_sensing"):
            raise ValueError("Task kind must be gnss or remote_sensing")
        if allowed_satellites and not set(allowed_satellites) <= set(s.satellites):
            raise ValueError("Unknown satellite in allowed host set")
        cpu = cpu_demand if cpu_demand is not None else (18 if kind == "gnss" else 30)
        duration = processing_s if processing_s is not None else (12 if kind == "gnss" else 20)
        size = output_mb if output_mb is not None else (4 if kind == "gnss" else 14)
        if not (5 <= cpu <= 75 and 1 <= duration <= 120 and .1 <= size <= 128
                and 1 <= priority <= 10 and 2 <= deadline_after_s <= 1800):
            raise ValueError("Task parameters outside supported bounds")
        tid = f"T{s.next_task:04d}"
        s.next_task += 1
        task = Task(tid, kind, region[:80], longitude_deg, priority, cpu,
                    cpu * duration, size, s.time_s, s.time_s + deadline_after_s,
                    campaign or tid, allowed_satellites=allowed_satellites)
        s.tasks[tid] = task
        s.log("task", f"New {'GNSS-R' if kind == 'gnss' else 'remote sensing'} task: {region}", task_id=tid)
        s.last_plan_tick = -100
        s.version += 1
        return task

    def add_campaign(self):
        s = self.state
        if len(s.active_tasks()) + 2 > s.config.max_active_tasks:
            raise ValueError("Not enough queue capacity for a two-product campaign")
        region, lon = s.rng.choice(REGIONS)
        cid = f"C{s.next_campaign:03d}"
        s.next_campaign += 1
        priority = s.rng.randint(4, 8)
        tasks = [self.add_task(kind=kind, region=region, longitude_deg=lon,
                 priority=priority, campaign=cid, deadline_after_s=210 + s.rng.randrange(30))
                 for kind in ("gnss", "remote_sensing")]
        return tasks

    def inject(self, node, kind, duration_s=None):
        inject_fault(self.state, node, kind, duration_s)
        self.monitor.evaluate(self.state.satellites[node], self.state)
        self._reconcile()
        self.state.last_plan_tick = -100
        self.state.version += 1

    def recover(self, node, restore_resources=True):
        clear_faults(self.state, self.monitor, node, restore_resources)
        self.state.version += 1

    def set_stress(self, node, cpu_pct=0, heat_w=0, drain_w=0, cooling_scale=1):
        sat = self.state.satellites[node]
        if not (0 <= cpu_pct <= 100 and 0 <= heat_w <= 120 and 0 <= drain_w <= 500
                and .1 <= cooling_scale <= 2):
            raise ValueError("Stress parameters outside supported bounds")
        sat.stress_cpu, sat.extra_heat_w = cpu_pct, heat_w
        sat.extra_drain_w, sat.cooling_scale = drain_w, cooling_scale
        self.state.last_plan_tick = -100
        self.state.log("injection", f"Stress: CPU {cpu_pct:g}%, heater {heat_w:g} W, drain {drain_w:g} W", node)
        self.state.version += 1

    def _cpu_ledger(self):
        for sat in self.state.satellites.values():
            sat.allocated_cpu = 0.0
        for task in self.state.tasks.values():
            if task.status == TaskStatus.RUNNING:
                self.state.satellites[task.owner].allocated_cpu += task.cpu_demand

    def _release_receiver(self, task):
        if task.receiver_reserved:
            sat = self.state.satellites[task.receiver_reserved]
            sat.storage_reserved_mb = max(0, sat.storage_reserved_mb - task.output_mb)
        task.receiver_reserved, task.transfer_mb = None, 0.0

    def _reconcile(self):
        s = self.state
        for task in s.tasks.values():
            if task.status == TaskStatus.RUNNING and not s.satellites[task.owner].can_compute:
                old = task.owner
                sat = s.satellites[old]
                sat.storage_reserved_mb = max(0, sat.storage_reserved_mb - task.output_mb)
                task.lost_work_cpu_s += task.progress_cpu_s
                task.progress_cpu_s = 0.0  # No fabricated checkpoint transfer.
                task.owner, task.route = None, None
                task.status = TaskStatus.QUEUED
                task.needs_repair = True
                if task.failure_time_s is None or task.recovery_recorded:
                    task.failure_time_s, task.recovery_recorded = s.time_s, False
                task.note = f"Retry required after {old} lost compute capability"
                s.log("repair", task.note, old, task.id)
                s.last_plan_tick = -100
            if task.status == TaskStatus.DOWNLINK and task.route and task.route.hops:
                hop = task.route.hops[0]
                endpoints = [s.satellites[x] for x in (hop.source, hop.target) if x != GROUND]
                if any(not x.can_relay for x in endpoints) or pair_key(hop.source, hop.target) in s.blocked_links:
                    self._release_receiver(task)
                    task.route = None
                    task.needs_repair = True
                    if task.failure_time_s is None or task.recovery_recorded:
                        task.failure_time_s, task.recovery_recorded = s.time_s, False
                    task.note = f"Data retained on {task.holder}; route repair required"
        self._cpu_ledger()

    def _record_task_recovery(self, task, at_s=None):
        if task.failure_time_s is not None and not task.recovery_recorded:
            self.state.recovery_delays_s.append((at_s if at_s is not None else self.state.time_s) - task.failure_time_s)
            self.state.counters["task_recovery_count"] += 1
            task.recovery_recorded = True

    def _admit(self, task, sat):
        s = self.state
        ok, reason = can_host(sat, task, s.time_s, s.config)
        if not ok:
            task.note = reason
            return False
        route = earliest_route(s, sat.id, task.output_mb, s.time_s + task.processing_s, task.deadline_s)
        if not route:
            task.note = "No predicted delivery route"
            return False
        sat.allocated_cpu += task.cpu_demand
        sat.storage_reserved_mb += task.output_mb
        # Later admission checks include this CPU load in their baseline forecast.
        # Actual energy is charged continuously by update_physics, never here.
        task.owner, task.assigned_s = sat.id, s.time_s
        task.status = TaskStatus.RUNNING
        if task.attempts:
            task.reassignments += 1
            s.counters["reassignments"] += 1
            self._record_task_recovery(task)
        task.attempts += 1
        task.needs_repair = False
        task.note = "Processing GNSS correlation map" if task.kind == "gnss" else "Acquiring and processing image"
        s.log("allocation", f"{task.id} -> {sat.id}: {task.cpu_demand:g}% CPU, {task.output_mb:g} MB reserved", sat.id, task.id)
        return True

    def _plan(self):
        s = self.state
        queued = sorted([t for t in s.tasks.values() if t.status == TaskStatus.QUEUED],
                        key=lambda t: (not t.needs_repair, -t.priority, t.deadline_s, t.id))[:s.config.candidate_limit]
        if not queued:
            return
        result = allocate(s, queued)
        repaired, stats = repair_placements(s, [t for t in queued if t.needs_repair], result)
        if stats:
            s.repair_stats = stats
        for task in queued:
            ranked = rank_hosts(s, task, result)
            if task.id in repaired:
                ranked.sort(key=lambda sat: sat.id != repaired[task.id])
            admitted = False
            for sat in ranked:
                if self._admit(task, sat):
                    admitted = True
                    break
            if not admitted:
                task.note = "Queued: no feasible host and delivery path"
        s.last_plan_tick = s.tick

    def _processing(self, dt):
        s = self.state
        for task in s.tasks.values():
            if task.status != TaskStatus.RUNNING:
                continue
            sat = s.satellites[task.owner]
            available = max(0, sat.cpu_capacity - sat.control_cpu - sat.stress_cpu)
            ratio = min(1.0, available / max(1e-9, sat.allocated_cpu))
            # External CPU stress throttles service, never creates spare cycles.
            task.progress_cpu_s = min(task.work_cpu_s, task.progress_cpu_s + task.cpu_demand * ratio * dt)
            if task.progress_cpu_s + 1e-7 >= task.work_cpu_s:
                task.status = TaskStatus.DOWNLINK
                task.holder = task.owner
                sat.storage_reserved_mb = max(0, sat.storage_reserved_mb - task.output_mb)
                sat.storage_used_mb += task.output_mb
                task.route = None
                task.note = f"Product buffered on {sat.id}"
                s.log("product", task.note, sat.id, task.id)

    def _transfers(self, dt):
        s = self.state
        edge_budget, radio_budget = tick_budgets(s, dt)
        initial_edges = edge_budget.copy()
        live = {link.key: link for link in active_links(s)}
        for sat in s.satellites.values():
            sat.tx_active = False
        # Priority first, deterministic FIFO within each priority; bounded queues.
        tasks = sorted([t for t in s.tasks.values() if t.status == TaskStatus.DOWNLINK],
                       key=lambda t: (-t.priority, t.created_s, t.id))
        for task in tasks:
            if s.time_s + dt > task.deadline_s + 1e-9:
                # Transfers complete on tick boundaries; do not report late delivery.
                continue
            holder = s.satellites[task.holder]
            if not holder.can_relay:
                task.note = f"Data retained on unavailable {holder.id}; awaiting recovery"
                continue
            if task.route and task.route.hops:
                hop = task.route.hops[0]
                key = pair_key(hop.source, hop.target)
                if s.time_s >= hop.end_s or (hop.start_s <= s.time_s and key not in live):
                    self._release_receiver(task)
                    task.route = None
                    task.needs_repair = True
            if not task.route or not task.route.hops:
                candidates = route_candidates(s, task.holder, task.output_mb, s.time_s, task.deadline_s)
                route = choose_repair_route(candidates, s) if task.needs_repair else (candidates[0] if candidates else None)
                task.route = route
                if not route:
                    task.note = f"Buffered on {task.holder}: no feasible contact path"
                    continue
                if task.needs_repair:
                    s.counters["reroutes"] += 1
                    s.log("route", "Repaired route: " + " -> ".join(route.nodes), task.holder, task.id)
                    # Recovery measured when useful transfer actually resumes below.
                task.needs_repair = False
            hop = task.route.hops[0]
            key = pair_key(hop.source, hop.target)
            if hop.start_s > s.time_s + 1e-8 or key not in live:
                task.note = f"Waiting for contact {hop.source} -> {hop.target}"
                continue
            if hop.target != GROUND:
                receiver = s.satellites[hop.target]
                if not receiver.can_relay:
                    continue
                if task.receiver_reserved != hop.target:
                    if receiver.free_storage_mb + 1e-8 < task.output_mb:
                        task.note = f"Waiting for receiver storage on {hop.target}"
                        continue
                    receiver.storage_reserved_mb += task.output_mb
                    task.receiver_reserved = hop.target
            amount = min(task.output_mb - task.transfer_mb, edge_budget[key],
                         radio_budget[hop.source], radio_budget[hop.target])
            if amount <= 1e-9:
                continue
            edge_budget[key] -= amount
            radio_budget[hop.source] -= amount
            radio_budget[hop.target] -= amount
            task.transfer_mb += amount
            holder.tx_active = True
            if hop.target != GROUND:
                s.satellites[hop.target].tx_active = True
            self._record_task_recovery(task, s.time_s + dt)
            task.note = f"{hop.source} -> {hop.target}: {task.transfer_mb:.1f}/{task.output_mb:g} MB"
            if task.transfer_mb + 1e-7 >= task.output_mb:
                holder.storage_used_mb = max(0, holder.storage_used_mb - task.output_mb)
                self._release_receiver(task)
                task.route.hops.pop(0)
                task.route.nodes.pop(0)
                if hop.target == GROUND:
                    task.holder = None
                    task.status = TaskStatus.COMPLETED
                    task.completed_s = s.time_s + dt
                    task.note = "Delivered to ground"
                    s.counters["delivered_mb"] += task.output_mb
                    s.log("delivery", f"Delivered {task.id}: {task.output_mb:g} MB", task.owner, task.id)
                else:
                    receiver.storage_used_mb += task.output_mb
                    task.holder = hop.target
        for key, capacity in initial_edges.items():
            sent = capacity - edge_budget[key]
            if sent > 0:
                s.transfer_log.append(dict(time_s=s.time_s, edge=key, sent_mb=sent, capacity_mb=capacity))

    def _expire(self):
        s = self.state
        for task in s.active_tasks():
            if s.time_s < task.deadline_s:
                continue
            if task.status == TaskStatus.RUNNING:
                sat = s.satellites[task.owner]
                sat.storage_reserved_mb = max(0, sat.storage_reserved_mb - task.output_mb)
            elif task.status == TaskStatus.DOWNLINK:
                sat = s.satellites[task.holder]
                sat.storage_used_mb = max(0, sat.storage_used_mb - task.output_mb)
                s.counters["dropped_mb"] += task.output_mb
                self._release_receiver(task)
            task.status = TaskStatus.MISSED
            task.route, task.holder = None, None
            task.note = "Deadline expired; partial product discarded"
            s.log("deadline", task.note, task.owner, task.id)
        self._cpu_ledger()

    def step(self, ticks=1):
        for _ in range(ticks):
            s, dt = self.state, self.state.config.dt_s
            expire_faults(s, self.monitor)
            self._reconcile()
            self._expire()
            if s.config.auto_tasks and s.time_s - s.last_arrival_s >= s.config.arrival_interval_s:
                if len(s.active_tasks()) + 2 <= s.config.max_active_tasks:
                    self.add_campaign()
                s.last_arrival_s = s.time_s
            if s.tick - s.last_plan_tick >= 2:
                self._plan()
            # Existing products transfer before newly acquired products enter storage.
            self._transfers(dt)
            self._processing(dt)
            end = s.time_s + dt
            for sat in s.satellites.values():
                s.counters["energy_used_wh"] += update_physics(sat, dt, end, s.rng, s.config)
            s.time_s = end
            s.tick += 1
            for sat in s.satellites.values():
                self.monitor.evaluate(sat, s)
            self._reconcile()
            self._expire()
            self._cpu_ledger()
            s.trim_tasks()
            s.version += 1
            metrics = summarize(s)
            s.history.append(dict(time_s=s.time_s, completed=metrics["completed"],
                 queued=metrics["queued"], temperature_c=metrics["max_temperature_c"],
                 battery_pct=metrics["mean_battery_pct"],
                 nodes={sat.id: dict(temperature_c=sat.telemetry.temperature_c,
                            cpu_pct=sat.telemetry.cpu_pct, battery_wh=sat.telemetry.battery_wh,
                            health=sat.health) for sat in s.satellites.values()}))
        return self.snapshot()

    def snapshot(self):
        snapshot = self.state.snapshot()
        snapshot["links"] = live_graph(self.state)
        return snapshot

    def validate(self):
        """Independent accounting assertions used by tests and headless runs."""
        s = self.state
        for sat in s.satellites.values():
            running = [t for t in s.tasks.values() if t.status == TaskStatus.RUNNING and t.owner == sat.id]
            held = sum(t.output_mb for t in s.tasks.values() if t.status == TaskStatus.DOWNLINK and t.holder == sat.id)
            reserved = sum(t.output_mb for t in running) + sum(t.output_mb for t in s.tasks.values() if t.receiver_reserved == sat.id)
            assert abs(sat.allocated_cpu - sum(t.cpu_demand for t in running)) < 1e-6, f"CPU ledger {sat.id}"
            assert abs(sat.storage_used_mb - held) < 1e-6, f"Stored data ledger {sat.id}"
            assert abs(sat.storage_reserved_mb - reserved) < 1e-6, f"Reservation ledger {sat.id}"
            assert sat.storage_used_mb + sat.storage_reserved_mb <= sat.storage_capacity_mb + 1e-6
            assert 0 <= sat.battery_wh <= sat.battery_capacity_wh
            assert math.isfinite(sat.temperature_c)
        for transfer in s.transfer_log:
            assert transfer["sent_mb"] <= transfer["capacity_mb"] + 1e-8
        for task in s.tasks.values():
            assert 0 <= task.progress_cpu_s <= task.work_cpu_s + 1e-8
            if task.status == TaskStatus.RUNNING:
                assert task.owner in s.satellites and s.satellites[task.owner].can_compute
            if task.status == TaskStatus.COMPLETED:
                assert task.holder is None and task.completed_s <= task.deadline_s + 1e-8
        return True
