"""Drawing-derived mooring equipment geometry for Carnival Panorama.

The longitudinal coordinates are reconstructed from the supplied mooring arrangement
drawing using the known mooring-platform frames and frame spacing. Fairleads are
ship-side equipment: for the current PORT-side model they are placed on the PORT
ship-side envelope and at the common deck elevation of their mooring station.
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

# Carnival Panorama reference dimensions used by the 3D ship model.
# PORT is +Y, therefore the nominal ship-side envelope is +Beam/2.
SHIP_BEAM_M = 37.20
PORT_SHIP_SIDE_Y_M = SHIP_BEAM_M / 2.0


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


# PORT-side fairlead reference points on Deck 3.
# The drawing supplies the longitudinal frame references; all fairleads at this
# mooring station are on the same deck/elevation and immediately adjacent to the
# PORT ship profile. Longitudinal frame references remain unchanged.
_FWD = [
    ("FWD-FL-20", 20, 358.0),
    ("FWD-FL-30", 30, 364.0),
    ("FWD-FL-22", 22, 369.0),
    ("FWD-FL-24", 24, 388.0),
    ("FWD-FL-26", 26, 392.0),
    ("FWD-FL-28", 28, 396.0),
    ("FWD-FL-18", 18, 400.0),
]

# PORT-side fairlead reference points on Deck 1.
# The drawing supplies the longitudinal frame references; all fairleads at this
# mooring station are on the same deck/elevation and immediately adjacent to the
# PORT ship profile.
_AFT = [
    ("AFT-FL-100", 100, -12.0),
    ("AFT-FL-102", 102, -8.0),
    ("AFT-FL-92", 92, -28.0),
    ("AFT-FL-94", 94, -32.0),
    ("AFT-FL-93", 93, -36.0),
    ("AFT-FL-91", 91, -40.0),
    ("AFT-FL-99", 99, -48.0),
    ("AFT-FL-101", 101, -52.0),
    ("AFT-FL-104", 104, -56.0),
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
        y_m=PORT_SHIP_SIDE_Y_M,
        z_m=FWD_PLATFORM_Z_M,
    )
    for pid, item, frame in _FWD
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
        y_m=PORT_SHIP_SIDE_Y_M,
        z_m=AFT_PLATFORM_Z_M,
    )
    for pid, item, frame in _AFT
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
        "FWD": {
            "frame_ref": FWD_PLATFORM_FRAME,
            "x_m": FWD_PLATFORM_X_M,
            "y_m": PORT_SHIP_SIDE_Y_M,
            "z_m": FWD_PLATFORM_Z_M,
            "deck": 3,
        },
        "AFT": {
            "frame_ref": AFT_PLATFORM_FRAME,
            "x_m": AFT_PLATFORM_X_M,
            "y_m": PORT_SHIP_SIDE_Y_M,
            "z_m": AFT_PLATFORM_Z_M,
            "deck": 1,
        },
    }
