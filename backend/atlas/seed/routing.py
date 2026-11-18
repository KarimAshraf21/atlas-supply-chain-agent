"""Maritime routing over a coarse sea graph of zones and chokepoints.

Used by the generator to decide which chokepoints a lane transits and how
long it takes, and to build contingency lanes that avoid chokepoints.
"""

from __future__ import annotations

import heapq
import math
from functools import cache

from .catalog import CHOKEPOINTS, PORTS, SEA_EDGES, SEA_ZONES

SEA_SPEED_KM_PER_DAY = 17 * 1.852 * 24  # 17 knots
ROUTE_FACTOR = 1.05  # waypoints already approximate the sailing track
PORT_HANDLING_DAYS = 3


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def _coord(node: str) -> tuple[float, float]:
    if node in SEA_ZONES:
        return SEA_ZONES[node]
    if node in CHOKEPOINTS:
        _, _, lat, lon, _ = CHOKEPOINTS[node]
        return lat, lon
    _, _, _, lat, lon, _, _ = PORTS[node]
    return lat, lon


@cache
def _adjacency() -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {}
    for a, b in SEA_EDGES:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    return adj


def sea_route(origin_port: str, dest_port: str, avoid: frozenset[str] = frozenset()) -> tuple[list[str], float] | None:
    """Shortest sea route as ``(waypoints, km)``; ``None`` if impossible when avoiding chokepoints."""
    start, goal = PORTS[origin_port][5], PORTS[dest_port][5]
    adj = _adjacency()
    dist = {start: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, start)]
    while heap:
        d, node = heapq.heappop(heap)
        if node == goal:
            break
        if d > dist.get(node, math.inf):
            continue
        for nxt in adj.get(node, []):
            if nxt in avoid:
                continue
            nd = d + haversine_km(_coord(node), _coord(nxt))
            if nd < dist.get(nxt, math.inf):
                dist[nxt], prev[nxt] = nd, node
                heapq.heappush(heap, (nd, nxt))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    km = haversine_km(_coord(origin_port), _coord(start)) + dist[goal] + haversine_km(_coord(goal), _coord(dest_port))
    return path, km


def chokepoints_on(path: list[str]) -> list[str]:
    return [n for n in path if n in CHOKEPOINTS]


def sea_days(km: float) -> int:
    return round(km * ROUTE_FACTOR / SEA_SPEED_KM_PER_DAY) + PORT_HANDLING_DAYS


def road_days(origin: tuple[float, float], dest: tuple[float, float]) -> int:
    return max(1, round(haversine_km(origin, dest) * 1.3 / 550))
