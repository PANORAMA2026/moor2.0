import pytest

from core.environmental_models import (
    AssumptionCoefficientProvider,
    ProjectedAreas,
    calculate_current_load,
    calculate_wind_load,
    combine_loads,
)


def test_zero_wind_returns_zero_load():
    load = calculate_wind_load(
        0.0, 90.0, ProjectedAreas(100.0, 200.0), 100.0,
        AssumptionCoefficientProvider(1.0, 1.0, 0.1),
    )
    assert load.fx_n == 0.0
    assert load.fy_n == 0.0
    assert load.mz_nm == 0.0


def test_loads_scale_with_speed_squared():
    provider = AssumptionCoefficientProvider(1.0, 0.0, 0.0)
    areas = ProjectedAreas(100.0, 200.0)
    a = calculate_wind_load(10.0, 0.0, areas, 100.0, provider)
    b = calculate_wind_load(20.0, 0.0, areas, 100.0, provider)
    assert b.fx_n == pytest.approx(4.0 * a.fx_n)


def test_combined_loads():
    p = AssumptionCoefficientProvider(1.0, 0.0, 0.0)
    a = calculate_current_load(1.0, 0.0, ProjectedAreas(10, 10), 10, p)
    b = calculate_current_load(1.0, 0.0, ProjectedAreas(10, 10), 10, p)
    c = combine_loads(a, b)
    assert c.fx_n == pytest.approx(a.fx_n * 2)
