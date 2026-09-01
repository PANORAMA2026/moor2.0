from datetime import datetime, timezone

from core.windy_point_forecast import _vector_speed_direction_to, _wind_from_direction, _timestamp_series


def test_current_vector_direction_to():
    speed, direction = _vector_speed_direction_to(1.0, 0.0)
    assert round(speed, 6) == 1.0
    assert round(direction, 6) == 90.0


def test_wind_vector_direction_from():
    speed, direction = _wind_from_direction(1.0, 0.0)
    assert round(speed, 6) == 1.0
    assert round(direction, 6) == 270.0


def test_timestamp_series_is_utc():
    ts = _timestamp_series({"ts": [0]})
    assert ts[0] == datetime(1970, 1, 1, tzinfo=timezone.utc)
