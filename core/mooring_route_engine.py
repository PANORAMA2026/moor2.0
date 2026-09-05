"""Traceable mooring route analysis.

Combines persistent route definition with component geometry. Reports known and
missing data and keeps geometry separate from friction/load assumptions.
"""
from __future__ import annotations
import math
import pandas as pd
from core.fairlead_contact_3d import solve_cylindrical_contact_3d
from core.mooring_geometry import get_components, get_connections, get_route_nodes, _bollard_point


def _point(df, component_id):
    if not component_id:return None
    rows=df[df.component_id.astype(str)==str(component_id)]
    if rows.empty:return None
    r=rows.iloc[0]; vals=[r.get("x_m"),r.get("y_m"),r.get("z_m")]
    return None if any(pd.isna(v) for v in vals) else tuple(float(v) for v in vals)


def _distance(a,b):
    return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))


def _angle(a,b):
    na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(x*x for x in b))
    if na<=1e-12 or nb<=1e-12:return None
    return math.degrees(math.acos(max(-1.,min(1.,sum(a[i]*b[i] for i in range(3))/(na*nb)))))


def analyze_route(station_name,line_id):
    components=get_components(station_name); connections=get_connections(station_name)
    rows=connections[connections.line_id.astype(str)==str(line_id)]
    if rows.empty:return {"status":"LINE_NOT_FOUND","line_id":line_id}
    row=rows.iloc[0]
    node_ids=get_route_nodes(station_name,line_id) or [str(row.get("winch_id")),str(row.get("fairlead_id"))]
    nodes=[]; missing=[]
    for seq,cid in enumerate(node_ids,1):
        p=_point(components,cid)
        if p is None:missing.append(cid); nodes.append({"sequence":seq,"component_id":cid,"coordinate_status":"MISSING"})
        else:nodes.append({"sequence":seq,"component_id":cid,"coordinate_status":"OK","point":p})
    bid=str(row.get("bollard_id")) if row.get("bollard_id") else None
    bp=_bollard_point(row.get("port_name"),bid)
    if bp is None:missing.append(f"BOLLARD:{bid}"); nodes.append({"sequence":len(nodes)+1,"component_id":f"BOLLARD:{bid}","coordinate_status":"MISSING"})
    else:nodes.append({"sequence":len(nodes)+1,"component_id":f"BOLLARD:{bid}","coordinate_status":"OK","point":bp})
    valid=[n for n in nodes if n.get("point") is not None]; complete=not missing and len(valid)>=2
    seg=[_distance(a["point"],b["point"]) for a,b in zip(valid,valid[1:])]
    result={"line_id":line_id,"port_name":row.get("port_name"),"nodes":nodes,"missing_coordinates":missing,"segment_lengths_m":seg,"line_length_m":sum(seg) if complete else None,"status":"COMPLETE" if complete else "INCOMPLETE","direction_changes":[],"fairlead_contact":None}
    if complete and len(valid)>=3:
        for i in range(1,len(valid)-1):
            prev,p,nxt=valid[i-1]["point"],valid[i]["point"],valid[i+1]["point"]
            result["direction_changes"].append({"component_id":valid[i]["component_id"],"angle_deg":_angle(tuple(prev[k]-p[k] for k in range(3)),tuple(nxt[k]-p[k] for k in range(3)))})
    fid=str(row.get("fairlead_id")) if row.get("fairlead_id") else None
    frows=components[components.component_id.astype(str)==fid] if fid else pd.DataFrame()
    if not frows.empty and complete:
        fr=frows.iloc[0]; diameter=fr.get("diameter_mm"); axis=(fr.get("axis_x"),fr.get("axis_y"),fr.get("axis_z")); idx=next((i for i,n in enumerate(valid) if n["component_id"]==fid),None)
        if idx is not None and 0<idx<len(valid)-1 and pd.notna(diameter) and float(diameter)>0 and all(pd.notna(v) for v in axis):
            result["fairlead_contact"]={"fairlead_id":fid,"diameter_mm":float(diameter),"axis":tuple(float(v) for v in axis),**solve_cylindrical_contact_3d(valid[idx-1]["point"],valid[idx+1]["point"],valid[idx]["point"],tuple(float(v) for v in axis),float(diameter))}
        else:result["fairlead_contact"]={"status":"FAIRLEAD_DIAMETER_OR_AXIS_REQUIRED","fairlead_id":fid}
    return result
