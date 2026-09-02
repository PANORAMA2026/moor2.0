"""Fixed berth geometry profiles reconstructed from onboard survey measurements.

Survey convention for the current berth data:
- X positive toward BOW.
- Y positive toward PORT (left when looking toward the bow).
- Z positive upward.
- Azimuth is unsigned: 0 deg = bow, 90 deg = abeam, 180 deg = stern.
- The berth is fixed; runtime ship positioning is a longitudinal ship offset only.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import cos, radians, sin
from typing import Dict, Tuple


@dataclass(frozen=True)
class BollardSurvey:
    bollard_id: str
    measurement_station: str  # FWD or AFT
    side: str                 # PORT or STBD
    distance_m: float
    slope_deg: float
    azimuth_deg: float


@dataclass(frozen=True)
class BollardPoint:
    bollard_id: str
    measurement_station: str
    side: str
    x_m: float
    y_m: float
    z_m: float
    survey_water_level_m: float


ENSENADA_PIER_2_SURVEY_LEVEL_M = 0.20
SHIP_LOA_M = 323.44
FWD_PLATFORM_X_M = SHIP_LOA_M / 2.0 - 27.0
AFT_PLATFORM_X_M = -SHIP_LOA_M / 2.0 + 14.0
FWD_PLATFORM_Z_M = 12.0
AFT_PLATFORM_Z_M = 7.5

# Ensenada Pier #2, all surveyed bollards are on PORT side.
ENSENADA_PIER_2_BOLLARDS: Tuple[BollardSurvey, ...] = (
    BollardSurvey("B1", "FWD", "PORT", 72.0, -7.0, 68.0),
    BollardSurvey("B2", "FWD", "PORT", 71.0, -7.0, 75.0),
    BollardSurvey("B3", "FWD", "PORT", 54.0, -10.0, 77.0),
    BollardSurvey("B4", "FWD", "PORT", 36.0, -16.0, 173.0),
    BollardSurvey("B1", "AFT", "PORT", 68.0, -5.0, 5.0),
    BollardSurvey("B2", "AFT", "PORT", 60.0, -4.0, 58.0),
    BollardSurvey("B3", "AFT", "PORT", 52.0, -4.0, 75.0),
    BollardSurvey("B4", "AFT", "PORT", 50.0, -4.0, 75.0),
    BollardSurvey("B5", "AFT", "PORT", 53.0, -4.0, 90.0),
    BollardSurvey("B6", "AFT", "PORT", 67.0, -4.0, 95.0),
    BollardSurvey("B7", "AFT", "PORT", 74.0, -2.0, 98.0),
    BollardSurvey("B8", "AFT", "PORT", 86.0, -2.0, 100.0),
)


def survey_to_local_xyz(survey: BollardSurvey) -> tuple[float, float, float]:
    """Convert the onboard range-finder convention into ship-reference XYZ."""
    if survey.measurement_station not in {"FWD", "AFT"}:
        raise ValueError("measurement_station must be FWD or AFT")
    if survey.side not in {"PORT", "STBD"}:
        raise ValueError("side must be PORT or STBD")
    if not 0.0 <= survey.azimuth_deg <= 180.0:
        raise ValueError("azimuth_deg must be between 0 and 180 degrees")

    horizontal = survey.distance_m * cos(radians(survey.slope_deg))
    # Same azimuth reference at FWD and AFT: 0=bow and 180=stern.
    dx = horizontal * cos(radians(survey.azimuth_deg))
    dy = horizontal * sin(radians(survey.azimuth_deg))
    if survey.side == "STBD":
        dy = -dy

    platform_x = FWD_PLATFORM_X_M if survey.measurement_station == "FWD" else AFT_PLATFORM_X_M
    platform_z = FWD_PLATFORM_Z_M if survey.measurement_station == "FWD" else AFT_PLATFORM_Z_M
    x = platform_x + dx
    z = platform_z + survey.distance_m * sin(radians(survey.slope_deg))
    return x, dy, z


def reconstruct_berth_points() -> Tuple[BollardPoint, ...]:
    return tuple(
        BollardPoint(
            s.bollard_id,
            s.measurement_station,
            s.side,
            *survey_to_local_xyz(s),
            ENSENADA_PIER_2_SURVEY_LEVEL_M,
        )
        for s in ENSENADA_PIER_2_BOLLARDS
    )


ENSENADA_PIER_2_POINTS = reconstruct_berth_points()

BERTH_PROFILES: Dict[str, Dict[str, object]] = {
    "Ensenada Pier #2": {
        "survey_water_level_m": ENSENADA_PIER_2_SURVEY_LEVEL_M,
        "bollards": ENSENADA_PIER_2_BOLLARDS,
        "points": ENSENADA_PIER_2_POINTS,
        "coordinate_system": {
            "x": "ship longitudinal axis; + toward bow",
            "y": "transverse axis; + PORT",
            "z": "vertical; + upward; platform absolute reference used for display",
            "positioning": "berth fixed; runtime ship uses longitudinal offset only",
            "survey_level": "+0.20 m water level reference",
        },
    }
}


def get_berth_profile(name: str) -> Dict[str, object]:
    try:
        return BERTH_PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown berth profile: {name}") from exc


def list_berth_profiles() -> list[str]:
    return sorted(BERTH_PROFILES)


def bollard_points_as_dicts(name: str = "Ensenada Pier #2") -> list[dict]:
    return [asdict(point) for point in get_berth_profile(name)["points"]]
