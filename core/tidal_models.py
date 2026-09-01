"""Tide and tidal-current state models for mooring analysis.

This module deliberately separates tidal data acquisition from the engineering
calculation. A tide height can be used to represent the quasi-static vertical
movement of the vessel only when the selected reference datum and vessel-heave
assumption are documented. Tidal current must be supplied as a vector from a
current provider or measurement; it must not be inferred from tide height alone
without a validated local hydrodynamic model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import hypot


@dataclass(frozen=True)
class TidalState:
    """Environmental tidal state at a mooring location.

    water_level_m is relative to the declared datum.
    tidal_current_u_mps is positive East and tidal_current_v_mps positive North.
    """

    timestamp_utc: datetime
    water_level_m: float | None = None
    datum: str | None = None
    tidal_current_u_mps: float | None = None
    tidal_current_v_mps: float | None = None
    source: str = "UNSPECIFIED"
    source_kind: str = "UNKNOWN"

    @property
    def tidal_current_speed_mps(self) -> float | None:
        if self.tidal_current_u_mps is None or self.tidal_current_v_mps is None:
            return None
        return hypot(self.tidal_current_u_mps, self.tidal_current_v_mps)

    @property
    def tidal_current_direction_to_deg(self) -> float | None:
        """Current vector direction toward, clockwise from true North."""
        if self.tidal_current_u_mps is None or self.tidal_current_v_mps is None:
            return None
        import math
        return (math.degrees(math.atan2(self.tidal_current_u_mps, self.tidal_current_v_mps)) + 360.0) % 360.0


def vessel_heave_from_tide(
    water_level_m: float,
    reference_water_level_m: float = 0.0,
    response_factor: float = 1.0,
) -> float:
    """Return the assumed vessel vertical displacement caused by tide.

    response_factor=1.0 is a transparent quasi-static assumption that the
    vessel follows the water-level change one-for-one. It is not a validated
    hydrodynamic response model and must be replaced if a measured/calculated
    heave response is available.
    """
    if not 0.0 <= response_factor <= 1.5:
        raise ValueError("Tide response factor must be between 0 and 1.5.")
    return (float(water_level_m) - float(reference_water_level_m)) * response_factor
