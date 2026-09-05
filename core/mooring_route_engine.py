"""Traceable mooring route analysis.

This module combines the persistent route definition with component geometry.
It reports what is known, what is missing, and which calculations are only
geometric. It deliberately does not invent friction coefficients or load values.
"""
from __future__ import annotations

import math
from typing import Dict, List

import pandas as pd

from core.fairlead_contact import tangent_contact_geometry
from core.mooring_geometry import get_components, get_connections, get_route_nodes, _bollard_point


def _point(df: pd.DataFrame, component_id: str):
    if not component_id:
        return None
    rows = df[df.component_id.astype(str) == str(component_id)]
    if rows.empty:
        return None
    r = rows.iloc[0]
    vals = [r.get("x_m"), r.get("y_m"), r.get("z_m")]
    if any(pd.isna(v) for v in vals):
        return None
    return tuple(float(v) for v in vals)


def _distance(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def analyze_route(station_name: str, line_id: str) -> Dict:
    components = get_components(station_name)
    connections = get_connections(station_name)
    rows = connections[connections.line_id.astype(str) == str(line_id)]
    if rows.empty:
        return {"status": "LINE_NOT_FOUND", "line_id": line_id}

    row = rows.iloc[0]
    node_ids = get_route_nodes(station_name, line_id)
    if not node_ids:
        node_ids = [str(row.get("winch_id")), str(row.get("fairlead_id"))]

    nodes: List[Dict] = []
    missing = []
    for seq, cid in enumerate(node_ids, 1):
        p = _point(components, cid)
        if p is None:
            missing.append(cid)
            nodes.append({"sequence": seq, "component_id": cid, "coordinate_status": "MISSING"})
        else:
            nodes.append({"sequence": seq, "component_id": cid, "coordinate_status": "OK", "point": p})

    bollard_id = str(row.get("bollard_id")) if row.get("bollard_id") else None
    bp = _bollard_point(row.get("port_name"), bollard_id)
    if bp is None:
        missing.append(f"BOLLARD:{bollard_id}")
        nodes.append({"sequence": len(nodes) + 1, "component_id": f"BOLLARD:{bollard_id}", "coordinate_status": "MISSING"})
    else:
        nodes.append({"sequence": len(nodes) + 1, "component_id": f"BOLLARD:{bollard_id}", "coordinate_status": "OK", "point": bp})

    valid = [n for n in nodes if n.get("point") is not None]
    segment_lengths = [_distance(a["point"], b["point"]) for a, b in zip(valid, valid[1:])]
    result = {
        "line_id": line_id,
        "port_name": row.get("port_name"),
        "nodes": nodes,
        "missing_coordinates": missing,
        "segment_lengths_m": segment_lengths,
        "line_length_m": sum(segment_lengths) if not missing and len(valid) >= 2 else None,
        "status": "COMPLETE" if not missing and len(valid) >= 2 else "INCOMPLETE",
        "direction_changes": [],
        "fairlead_contact": None,
    }

    if not missing and len(valid) >= 3:
        for i in range(1, len(valid) - 1):
            p_prev, p, p_next = valid[i - 1]["point"], valid[i]["point"], valid[i + 1]["point"]
            vin = tuple(p_prev[k] - p[k] for k in range(3))
            vout = tuple(p_next[k] - p[k] for k in range(3))
            nin = math.sqrt(sum(x*x for x in vin)); nout = math.sqrt(sum(x*x for x in vout))
            angle = None if nin <= 1e-12 or nout <= 1e-12 else math.degrees(math.acos(max(-1.0, min(1.0, sum(vin[k]*vout[k] for k in range(3))/(nin*nout)))))
            result["direction_changes"].append({"component_id": valid[i]["component_id"], "angle_deg": angle})

    # Contact geometry is evaluated only when the selected intermediate component
    # has a diameter and a usable local axis. No friction correction is applied.
    fairlead_id = row.get("fairlead_id")
    frows = components[components.component_id.astype(str) == str(fairlead_id)] if fairlead_id else pd.DataFrame()
    if not frows.empty and len(valid) >= 3:
        fr = frows.iloc[0]
        diameter = fr.get("diameter_mm")
        axis = (fr.get("axis_x"), fr.get("axis_y"), fr.get("axis_z"))
        if pd.notna(diameter) and float(diameter) > 0 and all(pd.notna(v) for v in axis):
            fair_idx = next((i for i, n in enumerate(valid) if n["component_id"] == str(fairlead_id)), None)
            if fair_idx is not None and 0 < fair_idx < len(valid) - 1:
                contact = tangent_contact_geometry(valid[fair_idx]["point"], float(diameter)/2.0, valid[fair_idx-1]["point"], valid[fair_idx+1]["point"], side=1)
                result["fairlead_contact"] = {"fairlead_id": str(fairlead_id), "diameter_mm": float(diameter), "axis": tuple(float(v) for v in axis), **contact}
        else:
            result["fairlead_contact"] = {"status": "FAIRLEAD_DIAMETER_OR_AXIS_REQUIRED", "fairlead_id": str(fairlead_id)}

    return result
