"""Mooring setup definitions built from onboard operating practice.

The setup topology is intentionally separated from physical fairlead/chock coordinates.
Those coordinates must be mapped from the vessel mooring-station drawing before they are
used for engineering line geometry or tension calculations.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class MooringLineAssignment:
    line_id: str
    ship_station: str
    line_type: str
    shore_bollard_id: str
    quantity: int
    fairlead_id: str | None = None
    chock_id: str | None = None
    notes: str = ""


# Ensenada Pier #2 — normal onboard setup supplied by operator.
# FWD: B1 x2, B2 x2, B3 x3, B4 x2 spring.
# AFT: B1 x2 spring, B3 x3, B4 x2, B6 x2.
ENSENADA_PIER_2_NORMAL_SETUP = (
    MooringLineAssignment("FWD-HL-B1", "FWD", "HEAD", "B1", 2),
    MooringLineAssignment("FWD-HL-B2", "FWD", "HEAD", "B2", 2),
    MooringLineAssignment("FWD-HL-B3", "FWD", "HEAD", "B3", 3),
    MooringLineAssignment("FWD-SP-B4", "FWD", "SPRING", "B4", 2),
    MooringLineAssignment("AFT-SP-B1", "AFT", "SPRING", "B1", 2),
    MooringLineAssignment("AFT-ST-B3", "AFT", "STERN", "B3", 3),
    MooringLineAssignment("AFT-ST-B4", "AFT", "STERN", "B4", 2),
    MooringLineAssignment("AFT-ST-B6", "AFT", "STERN", "B6", 2),
)

MOORING_SETUP_PROFILES = {
    "Ensenada Pier #2": {
        "name": "Normal Ensenada Pier #2",
        "description": "Normal onboard mooring arrangement supplied by operator",
        "assignments": ENSENADA_PIER_2_NORMAL_SETUP,
        "total_lines": 18,
        "source": "ONBOARD_OPERATOR_INPUT",
        "status": "TOPOLOGY_DEFINED_FAIRLEAD_MAPPING_PENDING",
    }
}


def get_mooring_setup(port_name: str = "Ensenada Pier #2") -> dict:
    profile = MOORING_SETUP_PROFILES[port_name]
    return {
        **profile,
        "assignments": tuple(asdict(a) for a in profile["assignments"]),
    }


def expand_line_assignments(port_name: str = "Ensenada Pier #2") -> list[dict]:
    """Expand grouped quantities into individual logical lines.

    Example: B1 x2 becomes two independent logical line records.  The records
    deliberately have no invented fairlead/chock coordinates.
    """
    expanded: list[dict] = []
    for assignment in MOORING_SETUP_PROFILES[port_name]["assignments"]:
        for n in range(1, assignment.quantity + 1):
            expanded.append({
                "line_id": f"{assignment.line_id}-{n:02d}",
                "ship_station": assignment.ship_station,
                "line_type": assignment.line_type,
                "shore_bollard_id": assignment.shore_bollard_id,
                "fairlead_id": assignment.fairlead_id,
                "chock_id": assignment.chock_id,
            })
    return expanded
