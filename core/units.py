"""Canonical engineering unit conversions.

Engineering calculations should use SI units internally.
Display conversion belongs at the UI boundary.
"""

KNOT_TO_MPS = 0.5144444444444445
STANDARD_GRAVITY = 9.80665
NEWTON_PER_KN = 1000.0


def knots_to_mps(value: float) -> float:
    return float(value) * KNOT_TO_MPS


def kn_to_tonne_force(value_kn: float) -> float:
    return float(value_kn) / STANDARD_GRAVITY


def tonne_force_to_kn(value_t: float) -> float:
    return float(value_t) * STANDARD_GRAVITY
