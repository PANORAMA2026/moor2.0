"""Deterministic fairlead contact geometry helpers.

The model is intentionally limited to the geometry that can be defended from
known coordinates: a circular roller cross-section in the plane normal to the
roller axis. It does not apply a friction coefficient or a capstan equation.
Those are separate engineering models and require justified input data.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

Point2 = Tuple[float, float]


def _norm(v: Point2) -> float:
    return math.hypot(v[0], v[1])


def _unit(v: Point2) -> Optional[Point2]:
    n = _norm(v)
    return None if n <= 1e-12 else (v[0] / n, v[1] / n)


def tangent_point_from_external_point(center: Point2, radius: float, external: Point2, side: int = 1) -> Optional[Point2]:
    """Return one tangent point from an external point to a circle.

    ``side`` selects the two mathematical tangent solutions (+1/-1). Returns
    None when the point is on/inside the circle or when radius is invalid.
    """
    if radius <= 0:
        return None
    dx, dy = external[0] - center[0], external[1] - center[1]
    d2 = dx * dx + dy * dy
    if d2 <= radius * radius + 1e-12:
        return None
    d = math.sqrt(d2)
    base = radius * radius / d2
    offset = radius * math.sqrt(max(0.0, d2 - radius * radius)) / d2
    return (
        center[0] + base * dx - side * offset * dy,
        center[1] + base * dy + side * offset * dx,
    )


def contact_angle_from_tangent_points(center: Point2, p1: Point2, p2: Point2) -> Optional[float]:
    """Central contact angle between two roller tangent points, in degrees."""
    a = (p1[0] - center[0], p1[1] - center[1])
    b = (p2[0] - center[0], p2[1] - center[1])
    na, nb = _norm(a), _norm(b)
    if na <= 1e-12 or nb <= 1e-12:
        return None
    c = max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))
    return math.degrees(math.acos(c))


def tangent_contact_geometry(center: Point2, radius: float, incoming: Point2, outgoing: Point2, side: int = 1) -> dict:
    """Solve the two tangent contacts and return a traceable geometry record."""
    p1 = tangent_point_from_external_point(center, radius, incoming, side)
    p2 = tangent_point_from_external_point(center, radius, outgoing, side)
    if p1 is None or p2 is None:
        return {
            "status": "POINT_NOT_EXTERNAL_TO_ROLLER",
            "contact_point_in": None,
            "contact_point_out": None,
            "contact_angle_deg": None,
        }
    return {
        "status": "GEOMETRY_ONLY",
        "contact_point_in": p1,
        "contact_point_out": p2,
        "contact_angle_deg": contact_angle_from_tangent_points(center, p1, p2),
    }
