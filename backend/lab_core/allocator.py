"""Two-block scaled ADMM (dual decomposition) for a convex admission relaxation.

min sum_ij c_ij x_ij + gamma/2 ||x||^2
subject to x_i in F_i = {0 <= x_i <= capability_i, A_i x_i <= b_i},
           x = z, z >= 0, sum_i z_ij <= 1.

Local x updates are independent satellite proximal QPs. z is the task consensus
projection. u is the scaled Lagrange multiplier: u <- u + x - z.
All agent messages are emulated in one process. No distributed networking or
asynchronous/partition-tolerant convergence claim is made.
"""
from __future__ import annotations

import time
import numpy as np

from .models import AllocationResult
from .network import earliest_route
from .resources import can_host, resource_rows, task_energy_wh

GAMMA = .3


def project_capped_simplex(values):
    """Projection onto nonnegative vectors whose sum is at most one."""
    y = np.maximum(values, 0)
    if y.sum() <= 1:
        return y
    order = np.sort(values)[::-1]
    cumulative = np.cumsum(order) - 1
    indices = np.arange(1, len(order) + 1)
    positive = np.flatnonzero(order - cumulative / indices > 0)
    theta = cumulative[positive[-1]] / (positive[-1] + 1)
    return np.maximum(values - theta, 0)


def project_local(values, A, b, caps, max_iterations=600):
    """Dykstra projection onto a box and four nonnegative halfspaces.

    Inner projections are numerical to tolerance, not a new ADMM block.
    Feasible integer reconstruction is always checked independently.
    """
    x = values.copy()
    corrections = np.zeros((len(b) + 1, len(values)))
    norms = np.sum(A * A, axis=1)
    for _ in range(max_iterations):
        previous = x.copy()
        y = x + corrections[0]
        x = np.clip(y, 0, caps)
        corrections[0] = y - x
        for k, (row, limit, norm) in enumerate(zip(A, b, norms), 1):
            y = x + corrections[k]
            excess = float(row @ y - limit)
            x = y - max(0, excess) * row / norm if norm > 1e-18 else y
            corrections[k] = y - x
        clipped = np.clip(x, 0, caps)
        feasible_error = np.max(A @ clipped - b, initial=0)
        if np.max(np.abs(x - previous), initial=0) < 1e-10 and feasible_error < 1e-9:
            break
    return np.clip(x, 0, caps)


def solve_relaxation(costs, matrices, budgets, caps, iterations=32, rho=2.0, tolerance=.005):
    n, m = costs.shape
    x = np.zeros((n, m))
    z = np.zeros_like(x)
    u = np.zeros_like(x)
    history = []
    if not m or not n:
        return x, z, history, True
    converged = False
    for iteration in range(1, iterations + 1):
        for i in range(n):
            center = (rho * (z[i] - u[i]) - costs[i]) / (rho + GAMMA)
            x[i] = project_local(center, matrices[i], budgets[i], caps[i])
        old_z = z.copy()
        for j in range(m):
            z[:, j] = project_capped_simplex(x[:, j] + u[:, j])
        u += x - z
        primal = float(np.linalg.norm(x - z))
        dual = float(rho * np.linalg.norm(z - old_z))
        history.append(dict(iteration=iteration, primal=primal, dual=dual))
        if primal <= tolerance and dual <= tolerance:
            converged = True
            break
    return x, z, history, converged


def allocate(state, tasks) -> AllocationResult:
    started = time.perf_counter()
    tasks = list(tasks)
    sats = list(state.satellites.values())
    n, m = len(sats), len(tasks)
    if not m:
        return state.allocator_result
    costs = np.zeros((n, m))
    caps = np.zeros((n, m))
    matrices, budgets = [], []
    for i, sat in enumerate(sats):
        A, b = resource_rows(sat, tasks, state.time_s, state.config)
        matrices.append(A)
        budgets.append(b)
        for j, task in enumerate(tasks):
            feasible, _ = can_host(sat, task, state.time_s, state.config)
            route = earliest_route(state, sat.id, task.output_mb,
                                   state.time_s + task.processing_s, task.deadline_s) if feasible else None
            caps[i, j] = float(feasible and route is not None)
            slack = max(1, task.deadline_s - state.time_s)
            utility = 1.2 + .38 * task.priority + min(2, task.processing_s / slack)
            cost = .4 * (1 - sat.battery_wh / 100) + .35 * sat.allocated_cpu / 100
            cost += .2 * max(0, sat.temperature_c - 40) / 30 + .2 * task_energy_wh(task)
            cost += .04 * route.cost if route else 0
            costs[i, j] = cost - utility
    c = state.config
    x, z, history, converged = solve_relaxation(costs, matrices, budgets, caps,
                        c.admm_iterations, c.admm_rho, c.admm_tolerance)
    violation = max([max(0.0, float(np.max(A @ row - b, initial=0)))
                     for A, b, row in zip(matrices, budgets, x)] or [0.0])
    result = AllocationResult(
        fractions={task.id: {sat.id: float(z[i, j]) for i, sat in enumerate(sats)}
                   for j, task in enumerate(tasks)},
        costs={task.id: {sat.id: float(costs[i, j]) for i, sat in enumerate(sats)}
               for j, task in enumerate(tasks)},
        iterations=len(history), primal_residual=history[-1]["primal"],
        dual_residual=history[-1]["dual"], converged=converged,
        runtime_ms=(time.perf_counter() - started) * 1000, history=history,
        local_constraint_violation=violation,
        objective=float(np.sum(costs * x) + GAMMA / 2 * np.sum(x * x)),
        message_scalars=3 * n * m * len(history))
    state.allocator_result = result
    return result


def rank_hosts(state, task, result):
    fractions = result.fractions.get(task.id, {})
    costs = result.costs.get(task.id, {})
    return sorted(state.satellites.values(),
                  key=lambda sat: (-fractions.get(sat.id, 0), costs.get(sat.id, 0), sat.id))
