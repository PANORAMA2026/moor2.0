"""Single orchestration entry point for the engineering mooring calculation.

This module deliberately separates three stages:
1. geometry (including explicit tidal vessel heave),
2. environmental loads (wind + total current),
3. line equilibrium and diagnostics.
"""

from __future__ import annotations

import pandas as pd

from core.environmental_engine import EnvironmentalLoadResult, VesselHydroGeometry
from core.environmental_state import EnvironmentalState
from core.hydrodynamic_forces import calculate_environmental_state_loads
from core.line_mechanics import solve_line_tensions_3d
from core.tidal_geometry import apply_vessel_heave_to_geometry
from core.tidal_models import vessel_heave_from_tide


def run_mooring_calculation(
    geom_df: pd.DataFrame,
    environmental_state: EnvironmentalState,
    vessel: VesselHydroGeometry,
    berth_heading_true_deg: float,
    wind_coefficients,
    current_coefficients,
    *,
    reference_water_level_m: float = 0.0,
    tide_response_factor: float = 1.0,
    pretension_pct: float = 10.0,
) -> tuple[pd.DataFrame, EnvironmentalLoadResult]:
    """Run geometry+tide+environment+equilibrium with traceable inputs."""
    heave = 0.0
    if environmental_state.water_level_m is not None:
        heave = vessel_heave_from_tide(
            environmental_state.water_level_m,
            reference_water_level_m=reference_water_level_m,
            response_factor=tide_response_factor,
        )
        geom_df = apply_vessel_heave_to_geometry(geom_df, heave)

    load_result = calculate_environmental_state_loads(
        environmental_state,
        afw=vessel.frontal_wind_area_m2,
        alw=vessel.lateral_wind_area_m2,
        beam=1.0,
        draft=1.0,
        loa=vessel.loa_m,
        berth_heading_true_deg=berth_heading_true_deg,
    )
    solver_result = solve_line_tensions_3d(
        geom_df,
        load_result.as_legacy_solver_dict(),
        pretension_pct=pretension_pct,
    )
    solver_result.attrs["environmental_state"] = environmental_state
    solver_result.attrs["vessel_heave_m"] = heave
    solver_result.attrs["environmental_load_result"] = load_result
    return solver_result, load_result
