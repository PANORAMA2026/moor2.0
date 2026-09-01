"""Compatibility facade for the normalized environmental-load engine.

The public legacy function ``calculate_environmental_forces`` is retained so
existing UI modules continue to work while all physics is routed through the
new SI-unit environmental engine.  Direction convention remains:
0° = bow/berth heading, 90° = starboard/right, 180° = stern, 270° = port/left.

The coefficient curves below preserve the project's historical assumptions.
They are explicitly NOT presented as class-approved or MEG4-certified tables.
"""

from __future__ import annotations

from math import cos, sin, radians

from core.environmental_engine import (
    EnvironmentalLoadResult,
    VesselHydroGeometry,
    calculate_environmental_loads,
)
from core.environmental_state import EnvironmentalState


def get_ocimf_wind_coefficients(angle_deg: float) -> tuple[float, float, float]:
    """Historical project wind coefficient curve, retained for compatibility."""
    rad = radians(angle_deg)
    return -0.55 * cos(rad), 0.92 * sin(rad), 0.18 * sin(2.0 * rad)


def get_ocimf_current_coefficients(angle_deg: float, wd_d_ratio: float = 3.0) -> tuple[float, float, float]:
    """Historical project current coefficient curve with shallow-water factor."""
    rad = radians(angle_deg)
    shallow_factor = 1.0
    if wd_d_ratio < 1.2:
        shallow_factor = 2.2
    elif wd_d_ratio < 1.5:
        shallow_factor = 1.6
    elif wd_d_ratio < 2.0:
        shallow_factor = 1.25
    return -0.08 * cos(rad), 0.88 * sin(rad) * shallow_factor, 0.15 * sin(2.0 * rad) * shallow_factor


class _WindProvider:
    def coefficients(self, relative_direction_deg: float):
        return get_ocimf_wind_coefficients(relative_direction_deg)


class _CurrentProvider:
    def __init__(self, wd_d_ratio: float = 3.0):
        self.wd_d_ratio = wd_d_ratio

    def coefficients(self, relative_direction_deg: float):
        return get_ocimf_current_coefficients(relative_direction_deg, self.wd_d_ratio)


def calculate_environmental_state_loads(
    state: EnvironmentalState,
    *,
    afw: float = 950.0,
    alw: float = 3200.0,
    beam: float = 37.2,
    draft: float = 8.25,
    loa: float = 323.44,
    berth_heading_true_deg: float = 0.0,
    wd_d_ratio: float = 3.0,
) -> EnvironmentalLoadResult:
    """Calculate loads directly from the normalized EnvironmentalState."""
    vessel = VesselHydroGeometry(
        frontal_wind_area_m2=afw,
        lateral_wind_area_m2=alw,
        frontal_submerged_area_m2=beam * draft,
        lateral_submerged_area_m2=loa * draft,
        loa_m=loa,
    )
    return calculate_environmental_loads(
        state,
        vessel,
        berth_heading_true_deg,
        _WindProvider(),
        _CurrentProvider(wd_d_ratio),
    )


def calculate_environmental_forces(
    v_wind: float,
    dir_wind: float,
    v_curr: float = 0.0,
    dir_curr: float = 0.0,
    afw: float = 950.0,
    alw: float = 3200.0,
    alc: float = 1800.0,
    loa: float = 323.44,
    beam: float = 37.2,
    draft: float = 8.25,
    wd_d_ratio: float = 3.0,
) -> dict[str, float]:
    """Legacy API adapter: knots in, tonne-force out.

    ``dir_wind`` and ``dir_curr`` are already expected in the berth-relative
    convention used by the historical UI.  Therefore the normalized state is
    represented with berth heading 0°.
    """
    state = EnvironmentalState(
        timestamp_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc),
        wind_speed_mps=float(v_wind) * 0.514444,
        wind_direction_from_deg_true=float(dir_wind) % 360.0,
        current_speed_mps=float(v_curr) * 0.514444,
        current_direction_to_deg_true=float(dir_curr) % 360.0,
        provider="LEGACY_UI_INPUT",
        source_kind="MANUAL",
    )
    result = calculate_environmental_state_loads(
        state,
        afw=afw,
        alw=alw,
        beam=beam,
        draft=draft,
        loa=loa,
        berth_heading_true_deg=0.0,
        wd_d_ratio=wd_d_ratio,
    )
    return result.as_legacy_solver_dict()
