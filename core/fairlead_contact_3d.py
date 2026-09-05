"""3D adapter for cylindrical fairlead contact geometry.

The cylinder is represented by its centre, axis and diameter. Approach/departure
points are projected onto the plane normal to the axis, solved as a 2D circle,
and the tangent points are lifted back into 3D. This is explicitly a planar
contact model; it is not a full 3D rope/roller contact solver.
"""
from __future__ import annotations
import math
from typing import Optional
from core.fairlead_contact import tangent_point_from_external_point, contact_angle_from_tangent_points


def _norm(v):
    return math.sqrt(sum(x*x for x in v))


def _dot(a,b):
    return sum(x*y for x,y in zip(a,b))


def _unit(v):
    n=_norm(v)
    return None if n <= 1e-12 else tuple(x/n for x in v)


def _cross(a,b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _sub(a,b):
    return tuple(a[i]-b[i] for i in range(3))


def solve_cylindrical_contact_3d(approach, departure, center, axis, diameter_mm):
    if diameter_mm <= 0:
        return {"status":"DIAMETER_INVALID"}
    au=_unit(axis)
    if au is None:
        return {"status":"AXIS_INVALID"}
    ref=_sub(approach,center)
    ref=_sub(ref,tuple(au[i]*_dot(ref,au) for i in range(3)))
    e1=_unit(ref)
    if e1 is None:
        for c in ((1.,0.,0.),(0.,1.,0.),(0.,0.,1.)):
            e1=_unit(_cross(au,c))
            if e1 is not None: break
    if e1 is None:
        return {"status":"BASIS_INVALID"}
    e2=_unit(_cross(au,e1))
    if e2 is None:
        return {"status":"BASIS_INVALID"}

    def project(p):
        rel=_sub(p,center)
        axial=_dot(rel,au)
        q=tuple(p[i]-axial*au[i] for i in range(3))
        qr=_sub(q,center)
        return (_dot(qr,e1),_dot(qr,e2))

    ap2=project(approach); dp2=project(departure); radius=diameter_mm/2.0
    t_in=tangent_point_from_external_point((0.,0.),radius,ap2,1)
    t_out=tangent_point_from_external_point((0.,0.),radius,dp2,1)
    if t_in is None or t_out is None:
        return {"status":"POINT_NOT_EXTERNAL_TO_ROLLER","radius_mm":radius,
                "approach_distance_mm":math.hypot(*ap2),"departure_distance_mm":math.hypot(*dp2)}

    def lift(q):
        return tuple(center[k]+q[0]*e1[k]+q[1]*e2[k] for k in range(3))
    cang=contact_angle_from_tangent_points((0.,0.),t_in,t_out)
    return {"status":"GEOMETRY_ONLY","model":"CYLINDRICAL_ROLLER_PLANAR",
            "radius_mm":radius,"contact_point_in":lift(t_in),"contact_point_out":lift(t_out),
            "contact_angle_deg":cang,"note":"Planar contact geometry; no friction/capstan correction."}
