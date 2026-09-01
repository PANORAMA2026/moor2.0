"""Canonical domain models for OpenMooring.

These models define stable interfaces between UI, persistence and engineering
calculations. Values use explicit units in field names where practical.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True)
class Ship:
    name: str
    loa_m: float
    beam_m: float
    draft_m: Optional[float] = None
    frontal_windage_area_m2: Optional[float] = None
    lateral_windage_area_m2: Optional[float] = None
    lateral_current_area_m2: Optional[float] = None


@dataclass(frozen=True)
class MooringLine:
    line_id: str
    line_name: str
    material: str
    mbl_tons: float
    main_length_m: float
    diameter_mm: Optional[float] = None
    tail_material: Optional[str] = None
    tail_mbl_tons: Optional[float] = None
    tail_length_m: float = 0.0
    certificate_id: Optional[str] = None
    wear_pct: float = 0.0


@dataclass(frozen=True)
class ConnectionPoint:
    point_id: str
    x_m: float
    y_m: float
    z_m: float = 0.0


@dataclass(frozen=True)
class Bollard(ConnectionPoint):
    swl_tons: Optional[float] = None
    status: str = "ACTIVE"


@dataclass(frozen=True)
class Environment:
    wind_speed_mps: float = 0.0
    wind_direction_deg: float = 0.0
    current_speed_mps: float = 0.0
    current_direction_deg: float = 0.0


@dataclass(frozen=True)
class SimulationInput:
    ship: Ship
    environment: Environment
    lines: Tuple[MooringLine, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LineResult:
    line_id: str
    tension_tons: float
    utilization_pct: float
    status: str


@dataclass(frozen=True)
class SimulationResult:
    success: bool
    line_results: Tuple[LineResult, ...] = field(default_factory=tuple)
    message: str = ""
    warnings: Tuple[str, ...] = field(default_factory=tuple)
