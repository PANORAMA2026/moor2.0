import numpy as np
import pandas as pd
import pytest

from core.line_mechanics import calculate_composite_stiffness, calculate_line_geometry, solve_line_tensions_3d
from core.solver_status import SolverStatus


def test_composite_stiffness_uses_tail_strength():
    k = calculate_composite_stiffness("HMPE", 100, 100, 10, "NYLON", 50, 10)
    assert k > 0


def test_tail_requires_valid_strength():
    with pytest.raises(ValueError):
        calculate_composite_stiffness("HMPE", 100, 100, 10, "NYLON", None, 10)


def test_missing_coordinate_is_rejected():
    lines = pd.DataFrame([{"bollard_id": "B1", "chock_x_m": 0, "chock_y_m": 0, "chock_z_m": 0}])
    bollards = pd.DataFrame([{"bollard_id": "B1", "x_m": 10, "y_m": 0}])
    with pytest.raises(ValueError):
        calculate_line_geometry(lines, bollards)


def test_solver_reports_singular_system():
    df = pd.DataFrame([{
        "line_id": "1", "mbl_tons": 100, "azimuth_deg": 0, "incline_deg": 0,
        "chock_x_m": 0, "chock_y_m": 0, "length_m": 100,
        "material": "HMPE", "tail_length_m": 0,
    }])
    result = solve_line_tensions_3d(df, {"Fx_total_t": 0, "Fy_total_t": 10, "Mz_total_tm": 0})
    assert result.attrs["solver_diagnostics"].status == SolverStatus.SINGULAR_SYSTEM
    assert np.isnan(result["Tension_tons"].iloc[0])
