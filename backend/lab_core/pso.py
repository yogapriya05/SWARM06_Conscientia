"""Bounded random-key PSO for orphan placement and contact-route alternatives.

Greedy reconstruction is the incumbent. Candidate schedules are decoded against
copied resource ledgers; only an improved feasible candidate replaces it.
Running jobs and data holders are outside the adjustable suffix.
"""
from __future__ import annotations

import copy
import time
import numpy as np

from .allocator import rank_hosts
from .network import earliest_route
from .resources import can_host


def _search(dimensions, evaluate, seed, particles, iterations):
    if not dimensions:
        return None, dict(iterations=0, evaluations=0, improved=False)
    rng = np.random.default_rng(seed)
    positions = rng.uniform(0, 1, (particles, dimensions))
    positions[0] = 0  # Keep the deterministic ADMM-ranked greedy incumbent.
    velocities = np.zeros_like(positions)
    scores, decoded = zip(*(evaluate(x) for x in positions))
    personal = positions.copy()
    personal_scores = np.array(scores)
    best_index = int(np.argmax(scores))
    best = positions[best_index].copy()
    best_score = scores[best_index]
    incumbent_score = scores[0]
    best_decoded = decoded[best_index]
    for _ in range(iterations):
        r1, r2 = rng.random(positions.shape), rng.random(positions.shape)
        velocities = .55 * velocities + 1.35 * r1 * (personal - positions) + 1.35 * r2 * (best - positions)
        positions = np.clip(positions + np.clip(velocities, -.35, .35), 0, .999999)
        for i in range(particles):
            score, proposal = evaluate(positions[i])
            if score > personal_scores[i] + 1e-10:
                personal_scores[i], personal[i] = score, positions[i].copy()
            if score > best_score + 1e-10:
                best_score, best, best_decoded = score, positions[i].copy(), proposal
    return best_decoded, dict(iterations=iterations, evaluations=particles * (iterations + 1),
                             improved=bool(best_score > incumbent_score + 1e-9),
                             incumbent_score=float(incumbent_score), best_score=float(best_score))


def repair_placements(state, tasks, result):
    started = time.perf_counter()
    # Bound the repair scope; other queued tasks use ADMM-ranked admission.
    tasks = sorted(tasks, key=lambda t: (-t.priority, t.deadline_s, t.id))[:8]
    if not tasks:
        return {}, {}
    hosts = {t.id: rank_hosts(state, t, result) for t in tasks}
    routes = {(t.id, sat.id): earliest_route(state, sat.id, t.output_mb,
               state.time_s + t.processing_s, t.deadline_s)
              for t in tasks for sat in hosts[t.id]}

    def evaluate(keys):
        ledger = {sat.id: copy.copy(sat) for sat in state.satellites.values()}
        proposal, score = {}, 0.0
        for j, task in enumerate(tasks):
            candidates = hosts[task.id]
            first = min(len(candidates) - 1, int(keys[j] * len(candidates)))
            # Rotated order preserves a feasible fallback for each particle.
            for sat in candidates[first:] + candidates[:first]:
                local = ledger[sat.id]
                route = routes[task.id, sat.id]
                if route and can_host(local, task, state.time_s, state.config)[0]:
                    local.allocated_cpu += task.cpu_demand
                    local.storage_reserved_mb += task.output_mb
                    proposal[task.id] = sat.id
                    score += 10 * task.priority - .15 * route.cost
                    score += result.fractions.get(task.id, {}).get(sat.id, 0)
                    break
        return score, proposal

    c = state.config
    proposal, stats = _search(len(tasks), evaluate, c.seed + state.tick,
                               c.pso_particles, c.pso_iterations)
    stats["runtime_ms"] = (time.perf_counter() - started) * 1000
    stats["scope_tasks"] = len(tasks)
    return proposal or {}, stats


def choose_repair_route(candidates, state):
    if not candidates:
        return None
    def evaluate(keys):
        index = min(len(candidates) - 1, int(keys[0] * len(candidates)))
        route = candidates[index]
        return -(route.arrival_s - state.time_s + 2 * route.cost), route
    route, _ = _search(1, evaluate, state.config.seed + state.tick,
                      state.config.pso_particles, state.config.pso_iterations)
    return route
