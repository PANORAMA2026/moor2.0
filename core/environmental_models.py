"""Traceable environmental load interfaces.

Equations are separated from coefficient providers so source-sensitive models
can be validated or replaced without changing solver integration.
All calculations in this module use SI units (N, m, s).
"""

from __future__ import annotations
from dataclasses import dataclass
from math import cos, sin, radians
from typing import Protocol


AIR_DENSITY_KG_M3 = 1.225
WATER_DENSITY_KG_M3 = 1025.0


@dataclass(frozen=True)
class LoadVector:
    fx_n: float
    fy_n: float
    mz_nm: float


class WindCoefficientProvider(Protocol):
    def coefficients(self, relative_direction_deg: float) -> tuple[float, float, float]:
        """Return (Cx, Cy, Cm) for the documented vessel/model basis."""


class CurrentCoefficientProvider(Protocol):
    def coefficients(self, relative_direction_deg: float) -> tuple[float, float, float]:
        """Return (Cx, Cy, Cm) for the documented vessel/model basis."""


@dataclass(frozen=True)
class AssumptionCoefficientProvider:
    """Generic symmetric coefficient provider.

    This provider is a temporary engineering assumption and MUST NOT be
    labelled as MEG4 validated. It exists to preserve a deterministic model
    while source-specific tables are pending.
    """

    longitudinal: float = 0.0
    transverse: float = 0.0
    moment: float = 0.0

    def coefficients(self, relative_direction_deg: float) -> tuple[float, float, float]:
        a = radians(relative_direction_deg)
        return (
            self.longitudinal * abs(cos(a)),
            self.transverse * sin(a),
            self.moment * sin(2.0 * a),
        )


@dataclass(frozen=True)
class ProjectedAreas:
    frontal_m2: float
    lateral_m2: float

    def validate(self) -> None:
        if self.frontal_m2 < 0 or self.lateral_m2 < 0:
            raise ValueError("Projected areas cannot be negative.")


def _validate_speed(speed_mps: float, label: str) -> None:
    if speed_mps < 0:
        raise ValueError(f"{label} cannot be negative.")


def calculate_wind_load(
    speed_mps: float,
    relative_direction_deg: float,
    areas: ProjectedAreas,
    reference_length_m: float,
    coefficients: WindCoefficientProvider,
    air_density_kg_m3: float = AIR_DENSITY_KG_M3,
) -> LoadVector:
    """Calculate steady wind force and yaw moment in SI units."""
    _validate_speed(speed_mps, "Wind speed")
    areas.validate()
    if reference_length_m <= 0:
        raise ValueError("Reference length must be greater than zero.")

    cx, cy, cm = coefficients.coefficients(relative_direction_deg)
    q = 0.5 * air_density_kg_m3 * speed_mps**2
    fx = q * areas.frontal_m2 * cx
    fy = q * areas.lateral_m2 * cy
    mz = q * areas.lateral_m2 * reference_length_m * cm
    return LoadVector(fx, fy, mz)


def calculate_current_load(
    speed_mps: float,
    relative_direction_deg: float,
    areas: ProjectedAreas,
    reference_length_m: float,
    coefficients: CurrentCoefficientProvider,
    water_density_kg_m3: float = WATER_DENSITY_KG_M3,
) -> LoadVector:
    """Calculate steady current force and yaw moment in SI units."""
    _validate_speed(speed_mps, "Current speed")
    areas.validate()
    if reference_length_m <= 0:
        raise ValueError("Reference length must be greater than zero.")

    cx, cy, cm = coefficients.coefficients(relative_direction_deg)
    q = 0.5 * water_density_kg_m3 * speed_mps**2
    fx = q * areas.frontal_m2 * cx
    fy = q * areas.lateral_m2 * cy
    mz = q * areas.lateral_m2 * reference_length_m * cm
    return LoadVector(fx, fy, mz)


def combine_loads(*loads: LoadVector) -> LoadVector:
    return LoadVector(
        fx_n=sum(load.fx_n for load in loads),
        fy_n=sum(load.fy_n for load in loads),
        mz_nm=sum(load.mz_nm for load in loads),
    )
