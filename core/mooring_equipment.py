"""Drawing-derived mooring equipment geometry for Carnival Panorama.

The coordinates are reconstructed from the supplied GA/mooring arrangement drawing.
Longitudinal X is anchored to the known FWD/AFT mooring-platform frames and converted
using the drawing frame spacing. Transverse coordinates are currently engineering
reference estimates from the same plan view and are explicitly marked as such; they
must be visually validated before being promoted to solver-grade geometry.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Literal


FrameSide = Literal["PORT", "STBD"]

FWD_FRAME_SPACING_M = 0.610
AFT_FRAME_SPACING_M = 0.725
FWD_PLATFORM_FRAME = 384.0
AFT_PLATFORM_FRAME = -24.0
FWD_PLATFORM_X_M = 134.72
AFT_PLATFORM_X_M = -147.72
FWD_PLATFORM_Z_M = 12.0
AFT_PLATFORM_Z_M = 7.5


@dataclass(frozen=True)
class MooringPoint:
    point_id: str
    station: str
    deck: int
    point_type: str
    equipment_item: int
    side: FrameSide
    frame_ref: float
    x_m: float
    y_m: float
    z_m: float
    source: str = "MOORING_ARRANGEMENT_DRAWING"
    confidence: str = "REFERENCE"


def _fwd_x(frame: float) -> float:
    return FWD_PLATFORM_X_M + (frame - FWD_PLATFORM_FRAME) * FWD_FRAME_SPACING_M


def _aft_x(frame: float) -> float:
    return AFT_PLATFORM_X_M + (frame - AFT_PLATFORM_FRAME) * AFT_FRAME_SPACING_M


# PORT-side universal fairlead reference points visible on Deck 3.
# Frame locations are read from the frame grid in the supplied drawing.
_FWD = [
    ("FWD-FL-20", 20, 358.0, 18.0),
    ("FWD-FL-30", 30, 364.0, 16.5),
    ("FWD-FL-22", 22, 369.0, 14.8),
    ("FWD-FL-24", 24, 388.0, 9.3),
    ("FWD-FL-26", 26, 392.0, 6.9),
    ("FWD-FL-28", 28, 396.0, 5.2),
    ("FWD-FL-18", 18, 400.0, 2.9),
]

# PORT-side universal fairlead reference points visible on Deck 1.
# The aft station datum is frame -24, consistent with the known 14 m aft-position
# relationship and the 725 mm frame spacing. Transverse values are reference estimates.
_AFT = [
    ("AFT-FL-100", 100, -12.0, 16.0),
    ("AFT-FL-102", 102, -8.0, 14.5),
    ("AFT-FL-92", 92, -28.0, 18.2),
    ("AFT-FL-94", 94, -32.0, 17.7),
    ("AFT-FL-93", 93, -36.0, 16.0),
    ("AFT-FL-91", 91, -40.0, 13.0),
    ("AFT-FL-99", 99, -48.0, 7.0),
    ("AFT-FL-101", 101, -52.0, 4.5),
    ("AFT-FL-104", 104, -56.0, 2.0),
]

FWD_PORT_FAIRLEADS = tuple(
    MooringPoint(
        point_id=pid,
        station="FWD",
        deck=3,
        point_type="FAIRLEAD",
        equipment_item=item,
        side="PORT",
        frame_ref=frame,
        x_m=_fwd_x(frame),
        y_m=y,
        z_m=FWD_PLATFORM_Z_M,
    )
    for pid, item, frame, y in _FWD
)

AFT_PORT_FAIRLEADS = tuple(
    MooringPoint(
        point_id=pid,
        station="AFT",
        deck=1,
        point_type="FAIRLEAD",
        equipment_item=item,
        side="PORT",
        frame_ref=frame,
        x_m=_aft_x(frame),
        y_m=y,
        z_m=AFT_PLATFORM_Z_M,
    )
    for pid, item, frame, y in _AFT
)

MOORING_FAIRLEADS = FWD_PORT_FAIRLEADS + AFT_PORT_FAIRLEADS


def fairlead_points_as_dicts() -> list[dict]:
    return [asdict(p) for p in MOORING_FAIRLEADS]


def get_fairleads(station: str | None = None, side: FrameSide | None = None) -> tuple[MooringPoint, ...]:
    points = MOORING_FAIRLEADS
    if station:
        points = tuple(p for p in points if p.station.upper() == station.upper())
    if side:
        points = tuple(p for p in points if p.side == side)
    return points


def get_mooring_platforms() -> dict[str, dict[str, float | int | str]]:
    return {
        "FWD": {"frame_ref": FWD_PLATFORM_FRAME, "x_m": FWD_PLATFORM_X_M, "y_m": 0.0, "z_m": FWD_PLATFORM_Z_M, "deck": 3},
        "AFT": {"frame_ref": AFT_PLATFORM_FRAME, "x_m": AFT_PLATFORM_X_M, "y_m": 0.0, "z_m": AFT_PLATFORM_Z_M, "deck": 1},
    }
