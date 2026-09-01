"""Engineering environmental-load orchestration.

This module is the bridge between the normalized EnvironmentalState and the
mooring equilibrium solver.  It keeps units, direction conventions, tidal
components and provenance explicit.  Coefficients are supplied by a provider
and are never silently labelled as class/MEG4 approved.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees, hypot, radians

from core.environmental_models import (
    AssumptionCoefficientProvider,
    LoadVector,
    ProjectedAreas,
    calculate_current_load,
    calculate_wind_load,
    combine_loads,
)
from core.environmental_state import EnvironmentalState
from core.environmental_adapters import load_vector_to_legacy


KNOT_TO_MPS = 0.514444


@dataclass(frozen=True)
class VesselHydroGeometry:
    frontal_wind_area_m2: float
    lateral_wind_area_m2: float
    frontal_submerged_area_m2: float
    lateral_submerged_area_m2: float
    loa_m: float

    def validate(self) -> None:
        for value, label in (
            (self.frontal_wind_area_m2, "frontal wind area"),
            (self.lateral_wind_area_m2, "lateral wind area"),
            (self.frontal_submerged_area_m2, "frontal submerged area"),
            (self.lateral_submerged_area_m2, "lateral submerged area"),
        ):
            if value < 0:
                raise ValueError(f"{label} cannot be negative")
        if self.loa_m <= 0:
            raise ValueError("LOA must be greater than zero")


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

    def as_legacy_solver_dict(self) -> dict[str, float]:
        result = load_vector_to_legacy(self.total)
        result.update({
            "Fx_wind_t": load_vector_to_legacy(self.wind)["Fx_total_t"],
            "Fy_wind_t": load_vector_to_legacy(self.wind)["Fy_total_t"],
            "Mz_wind_tm": load_vector_to_legacy(self.wind)["Mz_total_tm"],
            "Fx_current_t": load_vector_to_legacy(self.current)["Fx_total_t"],
            "Fy_current_t": load_vector_to_legacy(self.current)["Fy_total_t"],
            "Mz_current_tm": load_vector_to_legacy(self.current)["Mz_total_tm"],
        })
        return result


def _vector_speed_direction_to(u_mps: float, v_mps: float) -> tuple[float, float]:
    speed = hypot(u_mps, v_mps)
    if speed <= 1e-12:
        return 0.0, 0.0
    # Mathematical vector direction: 0=N, 90=E, direction the water flows toward.
    direction = (degrees(atan2(u_mps, v_mps)) + 360.0) % 360.0
    return speed, direction


def _direction_from_to_relative(direction_true_deg: float, berth_heading_deg: float, *, from_convention: bool) -> float:
    if from_convention:
        # Wind direction is where it comes from; convert to the vessel frame.
        return (direction_true_deg - berth_heading_deg) % 360.0
    return (direction_true_deg - berth_heading_deg) % 360.0


def calculate_environmental_loads(
    state: EnvironmentalState,
    vessel: VesselHydroGeometry,
    berth_heading_true_deg: float,
    wind_coefficients,
    current_coefficients,
) -> EnvironmentalLoadResult:
    """Calculate wind + total-current loads from one normalized state.

    The total current vector is used for hydrodynamic load.  If only tidal
    current is available it becomes the total current.  A tidal component is
    reported separately for traceability; it is never added twice to the load.
    """
    state.validate()
    vessel.validate()

    wind_speed = float(state.wind_speed_mps or 0.0)
    wind_dir = float(state.wind_direction_from_deg_true or 0.0)
    wind_relative = _direction_from_to_relative(wind_dir, berth_heading_true_deg, from_convention=True)
    wind = calculate_wind_load(
        wind_speed,
        wind_relative,
        ProjectedAreas(vessel.frontal_wind_area_m2, vessel.lateral_wind_area_m2),
        vessel.loa_m,
        wind_coefficients,
    )

    if state.current_speed_mps is not None and state.current_direction_to_deg_true is not None:
        current_speed = float(state.current_speed_mps)
        current_direction = float(state.current_direction_to_deg_true)
    elif state.tidal_current_u_mps is not None and state.tidal_current_v_mps is not None:
        current_speed, current_direction = _vector_speed_direction_to(
            float(state.tidal_current_u_mps), float(state.tidal_current_v_mps)
        )
    else:
        current_speed, current_direction = 0.0, 0.0

    current_relative = _direction_from_to_relative(current_direction, berth_heading_true_deg, from_convention=False)
    current = calculate_current_load(
        current_speed,
        current_relative,
        ProjectedAreas(vessel.frontal_submerged_area_m2, vessel.lateral_submerged_area_m2),
        vessel.loa_m,
        current_coefficients,
    )

    tidal_speed = 0.0
    tidal_direction = None
    if state.tidal_current_u_mps is not None and state.tidal_current_v_mps is not None:
        tidal_speed, tidal_direction = _vector_speed_direction_to(
            float(state.tidal_current_u_mps), float(state.tidal_current_v_mps)
        )

    return EnvironmentalLoadResult(
        wind=wind,
        current=current,
        total=combine_loads(wind, current),
        current_speed_mps=current_speed,
        current_direction_to_deg_true=current_direction,
        tidal_current_speed_mps=tidal_speed,
        tidal_current_direction_to_deg_true=tidal_direction,
        provenance=f"provider={state.provider}; source_kind={state.source_kind}",
    )


def default_legacy_assumption_providers():
    """Return explicit coefficient providers matching the legacy project model.

    These values preserve continuity during migration.  They are project
    assumptions, not a claim that the implementation is MEG4/class approved.
    """
    class WindProvider:
        def coefficients(self, relative_direction_deg):
            a = radians(relative_direction_deg)
            return -0.55 * __import__('math').cos(a), 0.92 * __import__('math').sin(a), 0.18 * __import__('math').sin(2 * a)

    class CurrentProvider:
        def coefficients(self, relative_direction_deg):
            a = radians(relative_direction_deg)
            return -0.08 * __import__('math').cos(a), 0.88 * __import__('math').sin(a), 0.15 * __import__('math').sin(2 * a)

    return WindProvider(), CurrentProvider()
