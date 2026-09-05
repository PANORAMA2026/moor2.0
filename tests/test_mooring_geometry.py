import math

from core.mooring_geometry import _angle_between
from core.fairlead_contact import (
    contact_angle_from_tangent_points,
    tangent_point_from_external_point,
    tangent_contact_geometry,
)
from core.fairlead_geometry import angle_between, d_over_d


def test_angle_between_perpendicular_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (0, 1, 0)), 90.0, abs_tol=1e-9)


def test_angle_between_parallel_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (2, 0, 0)), 0.0, abs_tol=1e-9)


def test_angle_between_opposite_vectors():
    assert math.isclose(_angle_between((1, 0, 0), (-1, 0, 0)), 180.0, abs_tol=1e-9)


def test_public_angle_between():
    assert math.isclose(angle_between((1, 0, 0), (0, 1, 0)), 90.0, abs_tol=1e-9)


def test_d_over_d():
    assert math.isclose(d_over_d(350.0, 70.0), 5.0, abs_tol=1e-9)
    assert d_over_d(None, 70.0) is None


def test_tangent_point_is_on_circle_and_tangent():
    center = (0.0, 0.0)
    radius = 1.0
    external = (3.0, 0.0)
    point = tangent_point_from_external_point(center, radius, external, 1)
    assert point is not None
    assert math.isclose(math.hypot(point[0], point[1]), radius, abs_tol=1e-9)
    radius_vector = point
    external_vector = (external[0] - point[0], external[1] - point[1])
    assert math.isclose(radius_vector[0] * external_vector[0] + radius_vector[1] * external_vector[1], 0.0, abs_tol=1e-9)


def test_contact_geometry_returns_angle():
    result = tangent_contact_geometry((0.0, 0.0), 1.0, (3.0, 0.0), (0.0, 3.0), 1)
    assert result["status"] == "GEOMETRY_ONLY"
    assert result["contact_angle_deg"] is not None
    assert 0.0 < result["contact_angle_deg"] < 180.0


def test_contact_angle_helper():
    angle = contact_angle_from_tangent_points((0.0, 0.0), (1.0, 0.0), (0.0, 1.0))
    assert math.isclose(angle, 90.0, abs_tol=1e-9)


def test_contact_geometry_rejects_internal_point():
    result = tangent_contact_geometry((0.0, 0.0), 2.0, (1.0, 0.0), (3.0, 0.0), 1)
    assert result["status"] == "POINT_NOT_EXTERNAL_TO_ROLLER"
    assert result["contact_angle_deg"] is None
