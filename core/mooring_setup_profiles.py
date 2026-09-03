"""Mooring setup topology for the Ensenada Pier #2 normal configuration.

A mooring connection is not a one-to-one winch-to-line or bollard-to-line
relationship. A single winch can serve multiple lines and a single bollard can
carry multiple lines, subject to the physical equipment capacity/SWL.
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
    winch_id: str | None = None
    winch_slot: int | None = None


# Four winches are available at each mooring station. Each physical winch may
# accommodate up to four lines; the actual line-to-winch assignment is left
# unpopulated until verified from onboard arrangement/inventory data.
FWD_WINCH_IDS = ("FWD-W1", "FWD-W2", "FWD-W3", "FWD-W4")
AFT_WINCH_IDS = ("AFT-W1", "AFT-W2", "AFT-W3", "AFT-W4")
WINCH_MAX_LINES_REFERENCE = 4

# Bollard loading is many-to-one: several lines may share a bollard. The
# permitted number of lines must be evaluated against the individual bollard
# SWL/MWLL and arrangement; no universal capacity is assumed here.

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
