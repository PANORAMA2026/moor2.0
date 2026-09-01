from datetime import datetime, timezone

import pandas as pd
import pytest

from core.tidal_models import TidalState, vessel_heave_from_tide
from core.tidal_geometry import apply_vessel_heave_to_geometry


def test_tidal_current_vector_properties():
    state = TidalState(
        timestamp_utc=datetime.now(timezone.utc),
        water_level_m=1.2,
        datum="CD",
        tidal_current_u_mps=0.3,
        tidal_current_v_mps=0.4,
    )
    assert state.tidal_current_speed_mps == pytest.approx(0.5)
    assert state.tidal_current_direction_to_deg == pytest.approx(36.8698976)


def test_vessel_heave_from_tide():
    assert vessel_heave_from_tide(2.0, 0.5) == pytest.approx(1.5)
    assert vessel_heave_from_tide(2.0, 0.5, response_factor=0.5) == pytest.approx(0.75)


def test_tidal_heave_changes_line_incline_and_length():
    geom = pd.DataFrame([
        {
            "bollard_x_m": 100.0,
            "bollard_y_m": 0.0,
            "bollard_z_m": 5.0,
            "chock_x_m": 0.0,
            "chock_y_m": 0.0,
            "chock_z_m": 10.0,
        }
    ])
    base = apply_vessel_heave_to_geometry(geom, 0.0)
    raised = apply_vessel_heave_to_geometry(geom, 2.0)

    assert raised.loc[0, "length_m"] > base.loc[0, "length_m"]
    assert raised.loc[0, "incline_deg"] > base.loc[0, "incline_deg"]
    assert raised.loc[0, "chock_z_effective_m"] == pytest.approx(12.0)
