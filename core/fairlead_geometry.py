"""Geometric fairlead/roller contact helpers.

This module is intentionally conservative. It calculates tangent/contact geometry
for a circular roller in a defined 2-D plane. It does not apply a friction or
capstan correction by itself. A real universal fairlead may contain several
rollers, so the selected roller and its axis must be known before this result is
used by the engineering solver.
"""
from __future__ import annotations
import math
from typing import Optional


def _norm(v):
    n=math.hypot(v[0],v[1])
    return n


def _angle(v):
    return math.atan2(v[1],v[0])


def _wrap_pi(a):
    while a<=-math.pi:a+=2*math.pi
    while a>math.pi:a-=2*math.pi
    return a


def circle_tangent_geometry(start_xy, end_xy, center_xy, radius_m: float) -> dict:
    """Return tangent points and minor/major arc options around a circular roller.

    start_xy/end_xy are the line-side points (e.g. winch and shore-side point)
    expressed in the plane normal to the roller axis. The function returns both
    possible tangent paths. The caller must select the physically correct side
    from the actual fairlead arrangement; this module never guesses it.
    """
    if radius_m<=0: raise ValueError("Roller radius must be positive")
    cx,cy=map(float,center_xy); s=(float(start_xy[0])-cx,float(start_xy[1])-cy); e=(float(end_xy[0])-cx,float(end_xy[1])-cy)
    ds,de=_norm(s),_norm(e)
    if ds<=radius_m or de<=radius_m:
        return {"status":"INVALID_GEOMETRY","reason":"Line-side point must lie outside the roller radius"}

    def tangents(v,d):
        base=_angle(v); alpha=math.acos(radius_m/d)
        return [base+alpha,base-alpha]

    ts=tangents(s,ds); te=tangents(e,de); candidates=[]
    for ai in ts:
        for aj in te:
            p1=(cx+radius_m*math.cos(ai),cy+radius_m*math.sin(ai))
            p2=(cx+radius_m*math.cos(aj),cy+radius_m*math.sin(aj))
            arc=abs(_wrap_pi(aj-ai))
            candidates.append({"start_tangent_angle_rad":ai,"end_tangent_angle_rad":aj,"start_contact":p1,"end_contact":p2,"wrap_angle_deg":math.degrees(arc),"tangent_length_m":math.sqrt(max(0,ds*ds-radius_m*radius_m))+math.sqrt(max(0,de*de-radius_m*radius_m)),"arc_length_m":radius_m*arc})
    candidates.sort(key=lambda x:x["tangent_length_m"]+x["arc_length_m"])
    return {"status":"TWO_SIDES_AVAILABLE","radius_m":radius_m,"candidates":candidates}


def select_contact_geometry(result: dict, side: str) -> Optional[dict]:
    if result.get("status")!="TWO_SIDES_AVAILABLE": return None
    if side not in {"candidate_1","candidate_2"}: raise ValueError("side must be candidate_1 or candidate_2")
    return result["candidates"][0 if side=="candidate_1" else 1]
