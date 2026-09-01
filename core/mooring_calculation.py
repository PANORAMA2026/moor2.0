"""Single orchestration entry point for geometry, environment and equilibrium."""
from __future__ import annotations
import pandas as pd
from core.environmental_engine import EnvironmentalLoadResult,VesselHydroGeometry,calculate_environmental_loads
from core.environmental_state import EnvironmentalState
from core.line_mechanics import solve_line_tensions_3d
from core.tidal_geometry import apply_vessel_heave_to_geometry
from core.tidal_models import vessel_heave_from_tide

def run_mooring_calculation(geom_df: pd.DataFrame, environmental_state: EnvironmentalState, vessel: VesselHydroGeometry, berth_heading_true_deg: float, wind_coefficients, current_coefficients, *, reference_water_level_m: float=0.0, tide_response_factor: float=1.0, pretension_pct: float=10.0) -> tuple[pd.DataFrame,EnvironmentalLoadResult]:
    """Run the complete engineering chain with explicit tidal geometry response."""
    heave=0.0
    if environmental_state.water_level_m is not None:
        heave=vessel_heave_from_tide(environmental_state.water_level_m,reference_water_level_m, tide_response_factor)
        geom_df=apply_vessel_heave_to_geometry(geom_df,heave)
    loads=calculate_environmental_loads(environmental_state,vessel,berth_heading_true_deg,wind_coefficients,current_coefficients)
    results=solve_line_tensions_3d(geom_df,loads.as_legacy_solver_dict(),pretension_pct=pretension_pct)
    results.attrs['environmental_state']=environmental_state
    results.attrs['vessel_heave_m']=heave
    results.attrs['environmental_load_result']=loads
    return results,loads
