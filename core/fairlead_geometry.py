"""Geometry helpers for mooring fairleads.

This module deliberately separates the centerline direction change from the
fairlead contact/wrap geometry. No friction correction is applied here.
"""
import math
from typing import Optional, Tuple

Vector3 = Tuple[float, float, float]


def vector(a: Vector3, b: Vector3) -> Vector3:
    return (b[0] - a[0], b[1] - a[1], b[2] - a[2])


def norm(v: Vector3) -> float:
    return math.sqrt(sum(x * x for x in v))


def angle_between(v1: Vector3, v2: Vector3) -> Optional[float]:
    n1, n2 = norm(v1), norm(v2)
    if n1 <= 1e-12 or n2 <= 1e-12:
        return None
    c = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2)) / (n1 * n2)))
    return math.degrees(math.acos(c))


def centerline_direction_change(winch: Vector3, fairlead: Vector3, bollard: Vector3) -> Optional[float]:
    """Angle between the two line centerline vectors at the fairlead.

    This is a direction-change angle only. It is NOT a claim about the actual
    contact/wrap angle around a cylindrical fairlead.
    """
    incoming = vector(fairlead, winch)
    outgoing = vector(fairlead, bollard)
    return angle_between(incoming, outgoing)


def d_over_d(fairlead_diameter_mm: Optional[float], rope_diameter_mm: Optional[float]) -> Optional[float]:
    if fairlead_diameter_mm is None or rope_diameter_mm is None or rope_diameter_mm <= 0:
        return None
    if fairlead_diameter_mm <= 0:
        return None
    return fairlead_diameter_mm / rope_diameter_mm


def bend_radius_mm(fairlead_diameter_mm: Optional[float]) -> Optional[float]:
    if fairlead_diameter_mm is None or fairlead_diameter_mm <= 0:
        return None
    return fairlead_diameter_mm / 2.0


def fairlead_geometry_status(fairlead_diameter_mm: Optional[float], rope_diameter_mm: Optional[float]) -> str:
    if fairlead_diameter_mm is None or fairlead_diameter_mm <= 0:
        return "DIAMETER_REQUIRED"
    if rope_diameter_mm is None or rope_diameter_mm <= 0:
        return "ROPE_DIAMETER_REQUIRED"
    return "READY_FOR_CONTACT_GEOMETRY"
