"""Flood-fill clustering of 2-D points.

Two points belong to the same cluster when they lie within a tolerance of
each other. Clustering is transitive: a chain of points, each close to the
next, forms a single cluster even if its ends are far apart.
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def cluster_points(points: list[Point], *, tolerance_mm: float) -> list[list[Point]]:
    """Group ``points`` into clusters by proximity.

    Args:
        points: 2-D points, in millimetres.
        tolerance_mm: two points join the same cluster when no further apart
            than this distance.

    Returns:
        A list of clusters; each cluster is a list of the points it contains.
        Every input point appears in exactly one cluster.
    """
    unvisited = [True] * len(points)
    clusters: list[list[Point]] = []

    for start in range(len(points)):
        if not unvisited[start]:
            continue
        cluster: list[Point] = []
        queue = [start]
        unvisited[start] = False
        while queue:
            cx, cy = points[queue.pop()]
            cluster.append((cx, cy))
            for other in range(len(points)):
                if not unvisited[other]:
                    continue
                ox, oy = points[other]
                if math.hypot(ox - cx, oy - cy) <= tolerance_mm:
                    unvisited[other] = False
                    queue.append(other)
        clusters.append(cluster)

    return clusters
