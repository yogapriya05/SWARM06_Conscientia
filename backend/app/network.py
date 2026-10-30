from __future__ import annotations

import math
from collections import deque
from typing import Iterable, Optional

from .models import ContactGraph, Satellite, SatelliteStatus


def distance(a: Satellite, b: Satellite) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a.position, b.position)))


def build_contact_graph(satellites: Iterable[Satellite], max_range_km: float = 2500) -> ContactGraph:
    sats = list(satellites)
    graph = ContactGraph({s.id: [] for s in sats})
    for i, first in enumerate(sats):
        if first.status != SatelliteStatus.ACTIVE:
            continue
        for second in sats[i + 1:]:
            if second.status == SatelliteStatus.ACTIVE and distance(first, second) <= max_range_km:
                graph.edges[first.id].append(second.id)
                graph.edges[second.id].append(first.id)
    for sat in sats:
        sat.neighbors = graph.edges[sat.id]
    return graph


def shortest_path(graph: ContactGraph, source: str, target: str) -> Optional[list[str]]:
    if source == target:
        return [source]
    queue = deque([(source, [source])])
    visited = {source}
    while queue:
        node, path = queue.popleft()
        for neighbor in graph.neighbors(node):
            if neighbor in visited:
                continue
            if neighbor == target:
                return path + [neighbor]
            visited.add(neighbor)
            queue.append((neighbor, path + [neighbor]))
    return None
