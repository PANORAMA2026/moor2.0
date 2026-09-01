"""Engineering environmental-load orchestration."""
from __future__ import annotations
from dataclasses import dataclass
from math import atan2, degrees, hypot, radians, cos, sin
from core.environmental_models import LoadVector, ProjectedAreas, calculate_current_load, calculate_wind_load, combine_loads
from core.environmental_state import EnvironmentalState
from core.environmental_adapters import load_vector_to_legacy

@dataclass(frozen=True)
class VesselHydroGeometry:
    frontal_wind_area_m2: float
    lateral_wind_area_m2: float
    frontal_submerged_area_m2: float
    lateral_submerged_area_m2: float
    loa_m: float
    def validate(self) -> None:
        for value, label in ((self.frontal_wind_area_m2,'frontal wind area'),(self.lateral_wind_area_m2,'lateral wind area'),(self.frontal_submerged_area_m2,'frontal submerged area'),(self.lateral_submerged_area_m2,'lateral submerged area')):
            if value < 0: raise ValueError(f"{label} cannot be negative")
        if self.loa_m <= 0: raise ValueError("LOA must be greater than zero")

@dataclass(frozen=True)
class EnvironmentalLoadResult:
    wind: LoadVector
    current: LoadVector
    total: LoadVector
    current_speed_mps: float
    current_direction_to_deg_true: float
    tidal_current_speed_mps: float
    tidal_current_direction_to_deg_true: float | None
    provenance: str
    def as_legacy_solver_dict(self) -> dict[str,float]:
        w,c,t=load_vector_to_legacy(self.wind),load_vector_to_legacy(self.current),load_vector_to_legacy(self.total)
        return {**t,"Fx_wind_t":w['Fx_total_t'],"Fy_wind_t":w['Fy_total_t'],"Mz_wind_tm":w['Mz_total_tm'],"Fx_current_t":c['Fx_total_t'],"Fy_current_t":c['Fy_total_t'],"Mz_current_tm":c['Mz_total_tm']}

def _vector_speed_direction_to(u_mps: float, v_mps: float) -> tuple[float,float]:
    speed=hypot(u_mps,v_mps)
    if speed <= 1e-12: return 0.0,0.0
    return speed,(degrees(atan2(u_mps,v_mps))+360.0)%360.0

def _relative(direction_true_deg: float, berth_heading_deg: float) -> float:
    return (direction_true_deg-berth_heading_deg)%360.0

def calculate_environmental_loads(state: EnvironmentalState, vessel: VesselHydroGeometry, berth_heading_true_deg: float, wind_coefficients, current_coefficients) -> EnvironmentalLoadResult:
    state.validate(); vessel.validate()
    wind=calculate_wind_load(float(state.wind_speed_mps or 0.0),_relative(float(state.wind_direction_from_deg_true or 0.0),berth_heading_true_deg),ProjectedAreas(vessel.frontal_wind_area_m2,vessel.lateral_wind_area_m2),vessel.loa_m,wind_coefficients)
    if state.current_speed_mps is not None and state.current_direction_to_deg_true is not None:
        current_speed=float(state.current_speed_mps); current_direction=float(state.current_direction_to_deg_true)
    elif state.tidal_current_u_mps is not None and state.tidal_current_v_mps is not None:
        current_speed,current_direction=_vector_speed_direction_to(float(state.tidal_current_u_mps),float(state.tidal_current_v_mps))
    else: current_speed,current_direction=0.0,0.0
    current=calculate_current_load(current_speed,_relative(current_direction,berth_heading_true_deg),ProjectedAreas(vessel.frontal_submerged_area_m2,vessel.lateral_submerged_area_m2),vessel.loa_m,current_coefficients)
    tidal_speed,tidal_direction=(0.0,None)
    if state.tidal_current_u_mps is not None and state.tidal_current_v_mps is not None:
        tidal_speed,tidal_direction=_vector_speed_direction_to(float(state.tidal_current_u_mps),float(state.tidal_current_v_mps))
    return EnvironmentalLoadResult(wind,current,combine_loads(wind,current),current_speed,current_direction,tidal_speed,tidal_direction,f"provider={state.provider}; source_kind={state.source_kind}")

class LegacyWindProvider:
    def coefficients(self, relative_direction_deg: float):
        a=radians(relative_direction_deg); return -0.55*cos(a),0.92*sin(a),0.18*sin(2*a)

class LegacyCurrentProvider:
    def __init__(self, wd_d_ratio: float=3.0): self.wd_d_ratio=wd_d_ratio
    def coefficients(self, relative_direction_deg: float):
        a=radians(relative_direction_deg); sf=2.2 if self.wd_d_ratio<1.2 else 1.6 if self.wd_d_ratio<1.5 else 1.25 if self.wd_d_ratio<2.0 else 1.0
        return -0.08*cos(a),0.88*sin(a)*sf,0.15*sin(2*a)*sf
