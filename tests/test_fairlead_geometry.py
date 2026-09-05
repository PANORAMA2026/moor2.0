import math
from core.fairlead_geometry import circle_tangent_geometry


def test_circle_tangent_geometry_returns_two_candidates():
    result=circle_tangent_geometry((10,0),(-10,0),(0,0),2)
    assert result["status"]=="TWO_SIDES_AVAILABLE"
    assert len(result["candidates"])==4
    assert all(c["wrap_angle_deg"]>=0 for c in result["candidates"])


def test_point_inside_roller_is_rejected():
    result=circle_tangent_geometry((1,0),(10,0),(0,0),2)
    assert result["status"]=="INVALID_GEOMETRY"
