"""Validation layer for mooring line routes.

A route is an ordered sequence of ship-side components followed by the shore
bollard. This module does not guess missing geometry and does not perform
friction/capstan corrections.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.mooring_geometry import get_components, get_connections, get_route_nodes, route_geometry


ALLOWED_ROUTE_TYPES = {
    "WINCH", "FAIRLEAD", "CHOCK", "CAPSTAN", "VERTICAL_GUIDE",
    "DOUBLE_VERTICAL_GUIDE", "EXTERNAL_ROLLER", "OTHER",
}


def validate_route(station_name: str, line_id: str) -> dict:
    """Return explicit validation findings for one stored mooring route."""
    components = get_components(station_name)
    connections = get_connections(station_name)
    row = connections[connections["line_id"].astype(str) == str(line_id)]
    errors = []
    warnings = []

    if row.empty:
        return {"status": "ERROR", "errors": ["LINE_NOT_DEFINED"], "warnings": [], "nodes": []}

    r = row.iloc[0]
    nodes = get_route_nodes(station_name, line_id)
    if not nodes:
        nodes = [str(r.get("winch_id")), str(r.get("fairlead_id"))]

    lookup = {str(x.component_id): x for x in components.itertuples()}
    if not nodes or nodes[0] in ("None", "nan", ""):
        errors.append("WINCH_NOT_DEFINED")
    elif nodes[0] not in lookup:
        errors.append(f"COMPONENT_NOT_FOUND:{nodes[0]}")
    elif str(lookup[nodes[0]].component_type) != "WINCH":
        errors.append("ROUTE_MUST_START_AT_WINCH")

    for cid in nodes[1:]:
        if cid not in lookup:
            errors.append(f"COMPONENT_NOT_FOUND:{cid}")
            continue
        if str(lookup[cid].component_type) not in ALLOWED_ROUTE_TYPES:
            errors.append(f"UNSUPPORTED_COMPONENT_TYPE:{cid}")

    if not r.get("bollard_id"):
        errors.append("BOLLARD_NOT_DEFINED")
    if not r.get("port_name"):
        errors.append("PORT_NOT_DEFINED")

    geo = route_geometry(station_name, line_id)
    if geo.get("missing_coordinates"):
        warnings.append("MISSING_COORDINATES:" + ",".join(geo["missing_coordinates"]))
    if geo.get("status") != "COMPLETE":
        warnings.append("GEOMETRY_INCOMPLETE")

    if len(nodes) < 2:
        warnings.append("NO_INTERMEDIATE_ROUTE_COMPONENTS")

    return {
        "status": "ERROR" if errors else ("WARNING" if warnings else "OK"),
        "errors": errors,
        "warnings": warnings,
        "nodes": nodes,
        "geometry": geo,
    }


def validate_station(station_name: str) -> pd.DataFrame:
    """Validate all stored lines in a station for use by an audit/report UI."""
    rows = []
    for line_id in get_connections(station_name).get("line_id", pd.Series(dtype=str)).astype(str):
        result = validate_route(station_name, line_id)
        rows.append({
            "line_id": line_id,
            "status": result["status"],
            "errors": "; ".join(result["errors"]),
            "warnings": "; ".join(result["warnings"]),
            "line_length_m": result.get("geometry", {}).get("line_length_m"),
            "nodes": " → ".join(result["nodes"]),
        })
    return pd.DataFrame(rows, columns=["line_id", "status", "errors", "warnings", "line_length_m", "nodes"])
