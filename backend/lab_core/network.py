"""Synthetic contact plan, time-dependent routing and live capacity accounting.

The graph is reciprocal. Rates are effective goodput after a fixed loss factor;
the simulator does not implement a radio waveform or the CCSDS SABR protocol.
"""
from __future__ import annotations

import heapq
import math
from itertools import combinations

from .models import Hop, Link, Route

GROUND = "GROUND"


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted((a, b)))


def _windows(now: float, horizon: float, period: float, width: float, offset: float):
    first = math.floor((now + offset) / period) - 1
    for cycle in range(first, first + math.ceil(horizon / period) + 3):
        start = cycle * period - offset
        end = start + width
        if end > now and start <= now + horizon:
            yield max(now, start), min(now + horizon, end)


def contacts(state, horizon_s: float = 180.0) -> list[Link]:
    now, nodes = state.time_s, list(state.satellites.values())
    n = len(nodes)
    links = []

    def add(a, b, windows, rate, loss, delay):
        key = pair_key(a, b)
        if key in state.blocked_links:
            return
        endpoints = [state.satellites[x] for x in (a, b) if x != GROUND]
        if any(not sat.can_relay for sat in endpoints):
            return
        energy_penalty = sum(1 - sat.battery_wh / 100 for sat in endpoints)
        heat_penalty = sum(max(0, sat.temperature_c - 55) / 25 for sat in endpoints)
        # Dimensionless relative edge cost. Coefficients are demo design choices.
        weight = .45 * delay / .1 + .25 * energy_penalty + .2 * loss / .1 + .1 * heat_penalty
        for start, end in windows:
            if end > start:
                links.append(Link(a, b, start, end, rate * (1 - loss), delay, loss, weight))

    for a, b in combinations(nodes, 2):
        separation = min((a.index - b.index) % n, (b.index - a.index) % n)
        if separation == 1:
            windows = [(now, now + horizon_s)]
        elif separation == 2 or n <= 6:
            windows = list(_windows(now, horizon_s, 80, 45, 7 * (a.index + b.index)))
        else:
            continue
        add(a.id, b.id, windows, 18 + 2 * ((a.index + b.index) % 4), .01 + .01 * (separation > 1), .02 + separation * .005)
    add(nodes[0].id, GROUND, [(now, now + horizon_s)], 22, .01, .04)
    other = nodes[n // 2]
    add(other.id, GROUND, list(_windows(now, horizon_s, 100, 55, 20)), 26, .02, .04)
    return links


def active_links(state) -> list[Link]:
    return [link for link in contacts(state) if link.start_s <= state.time_s < link.end_s]


def earliest_route(state, source: str, size_mb: float, ready_s: float,
                   deadline_s: float, banned: set[str] | None = None) -> Route | None:
    if source == GROUND:
        return Route([GROUND], [], ready_s, 0)
    if source not in state.satellites or not state.satellites[source].can_relay:
        return None
    banned = banned or set()
    graph: dict[str, list] = {}
    for link in contacts(state, max(1, min(240, deadline_s - state.time_s))):
        if link.key in banned:
            continue
        graph.setdefault(link.source, []).append((link.target, link))
        graph.setdefault(link.target, []).append((link.source, link))
    queue = [(ready_s, 0.0, source, [source], [])]
    best = {source: ready_s}
    # Positive propagation and serialization yield a FIFO temporal network.
    while queue:
        arrival, cost, node, path, hops = heapq.heappop(queue)
        if arrival > best.get(node, math.inf) + 1e-9:
            continue
        if node == GROUND:
            return Route(path, hops, arrival, cost)
        for target, link in graph.get(node, []):
            if target in path:
                continue
            if target != GROUND and state.satellites[target].free_storage_mb + 1e-8 < size_mb:
                continue
            start = max(arrival, link.start_s)
            finish = start + 8 * size_mb / link.rate_mbps + link.latency_s
            if finish > min(link.end_s, deadline_s) + 1e-9:
                continue
            if finish + 1e-9 < best.get(target, math.inf):
                best[target] = finish
                hop = Hop(node, target, start, link.end_s, link.rate_mbps, link.weight)
                heapq.heappush(queue, (finish, cost + link.weight, target, path + [target], hops + [hop]))
    return None


def route_candidates(state, source, size_mb, ready_s, deadline_s, limit=3):
    first = earliest_route(state, source, size_mb, ready_s, deadline_s)
    if not first:
        return []
    candidates = [first]
    signatures = {tuple(first.nodes)}
    for hop in first.hops:
        route = earliest_route(state, source, size_mb, ready_s, deadline_s,
                               {pair_key(hop.source, hop.target)})
        if route and tuple(route.nodes) not in signatures:
            candidates.append(route)
            signatures.add(tuple(route.nodes))
        if len(candidates) >= limit:
            break
    return sorted(candidates, key=lambda route: (route.arrival_s, route.cost))


def live_graph(state):
    rows = []
    for link in active_links(state):
        rows.append(dict(source=link.source, target=link.target, rate_mbps=link.rate_mbps,
                         weight=link.weight, end_s=link.end_s, key=link.key))
    return rows


def tick_budgets(state, dt):
    # A physical pair is half-duplex; each satellite has one shared 24 Mbps radio.
    edges = {link.key: link.rate_mbps * max(0, min(dt, link.end_s - state.time_s) - link.latency_s) / 8
             for link in active_links(state)}
    radios = {node: 24 * dt / 8 for node in state.satellites}
    radios[GROUND] = 48 * dt / 8
    return edges, radios
