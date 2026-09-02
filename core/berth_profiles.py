"""Fixed berth geometry profiles reconstructed from onboard survey measurements.

Survey coordinates are stored relative to the vessel mooring-platform reference
used during the original range-finder survey.  The berth remains fixed; the
runtime ship model may later be translated longitudinally by the operator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class BollardSurvey:
    bollard_id: str
    measurement_station: str  # FWD or AFT
    side: str                 # PORT or STBD
    distance_m: float
    slope_deg: float
    azimuth_deg: float


# Ensenada Pier #2, PORT side. Surveyed at +0.20 m water level.
# Azimuth convention: 0 deg = forward; 90 deg = abeam; 90-180 deg = aft sector.
ENSENADA_PIER_2_SURVEY_LEVEL_M = 0.20

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

BERTH_PROFILES: Dict[str, Dict[str, object]] = {
    "Ensenada Pier #2": {
        "survey_water_level_m": ENSENADA_PIER_2_SURVEY_LEVEL_M,
        "bollards": ENSENADA_PIER_2_BOLLARDS,
    }
}


def get_berth_profile(name: str) -> Dict[str, object]:
    """Return a fixed berth profile by configured name."""
    try:
        return BERTH_PROFILES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown berth profile: {name}") from exc


def list_berth_profiles() -> list[str]:
    return sorted(BERTH_PROFILES)
