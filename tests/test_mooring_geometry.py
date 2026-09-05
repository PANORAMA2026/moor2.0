import math

from core.mooring_geometry import _angle_between


def test_angle_between_perpendicular_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (0, 1, 0)), 90.0, abs_tol=1e-9)


def test_angle_between_parallel_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (2, 0, 0)), 0.0, abs_tol=1e-9)


def test_angle_between_opposite_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (-1, 0, 0)), 180.0, abs_tol=1e-9)
