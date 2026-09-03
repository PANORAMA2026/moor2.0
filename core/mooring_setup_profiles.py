"""Mooring setup topology for the Ensenada Pier #2 normal configuration.

This module defines the current operational line-to-bollard topology supplied by the
vessel team. Fairlead identifiers refer to the drawing-derived reference geometry in
core.mooring_equipment. The topology is intentionally separate from the numerical
solver so it can later be edited and saved as alternative setups.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MooringConnection:
    line_id: str
    station: str
    line_type: str
    fairlead_id: str
    bollard_id: str
    bollard_station: str
    side: str = "PORT"
    status: str = "REFERENCE"


# Ensenada Pier #2 — normal setup supplied by vessel team.
# FWD: B1 x2, B2 x2, B3 x3, B4 spring x2.
# AFT: B1 spring x2, B3 x3, B4 x2, B6 x2.
ENSENADA_PIER_2_NORMAL_SETUP = (
    MooringConnection("ENS-F01", "FWD", "HEAD", "FWD-FL-28", "B1", "FWD"),
    MooringConnection("ENS-F02", "FWD", "HEAD", "FWD-FL-18", "B1", "FWD"),
    MooringConnection("ENS-F03", "FWD", "HEAD", "FWD-FL-26", "B2", "FWD"),
    MooringConnection("ENS-F04", "FWD", "HEAD", "FWD-FL-24", "B2", "FWD"),
    MooringConnection("ENS-F05", "FWD", "HEAD", "FWD-FL-22", "B3", "FWD"),
    MooringConnection("ENS-F06", "FWD", "HEAD", "FWD-FL-30", "B3", "FWD"),
    MooringConnection("ENS-F07", "FWD", "HEAD", "FWD-FL-20", "B3", "FWD"),
    MooringConnection("ENS-F08", "FWD", "SPRING", "FWD-FL-30", "B4", "FWD"),
    MooringConnection("ENS-F09", "FWD", "SPRING", "FWD-FL-20", "B4", "FWD"),
    MooringConnection("ENS-A01", "AFT", "SPRING", "AFT-FL-100", "B1", "AFT"),
    MooringConnection("ENS-A02", "AFT", "SPRING", "AFT-FL-102", "B1", "AFT"),
    MooringConnection("ENS-A03", "AFT", "STERN", "AFT-FL-92", "B3", "AFT"),
    MooringConnection("ENS-A04", "AFT", "STERN", "AFT-FL-94", "B3", "AFT"),
    MooringConnection("ENS-A05", "AFT", "STERN", "AFT-FL-93", "B3", "AFT"),
    MooringConnection("ENS-A06", "AFT", "STERN", "AFT-FL-91", "B4", "AFT"),
    MooringConnection("ENS-A07", "AFT", "STERN", "AFT-FL-99", "B4", "AFT"),
    MooringConnection("ENS-A08", "AFT", "STERN", "AFT-FL-101", "B6", "AFT"),
    MooringConnection("ENS-A09", "AFT", "STERN", "AFT-FL-104", "B6", "AFT"),
)


def get_normal_setup() -> tuple[MooringConnection, ...]:
    return ENSENADA_PIER_2_NORMAL_SETUP


def setup_as_dicts() -> list[dict]:
    return [asdict(item) for item in ENSENADA_PIER_2_NORMAL_SETUP]


def setup_counts() -> dict[str, int]:
    return {
        "FWD": sum(1 for x in ENSENADA_PIER_2_NORMAL_SETUP if x.station == "FWD"),
        "AFT": sum(1 for x in ENSENADA_PIER_2_NORMAL_SETUP if x.station == "AFT"),
        "TOTAL": len(ENSENADA_PIER_2_NORMAL_SETUP),
    }
