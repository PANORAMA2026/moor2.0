"""Canonical geometry/configuration layer for the interactive mooring plan."""
import math, sqlite3
from typing import Optional, Sequence
import pandas as pd
from config.constants import DB_FILE_PATH

COMPONENT_TYPES=["WINCH","FAIRLEAD","CHOCK","CAPSTAN","BOLLARD","VERTICAL_GUIDE","DOUBLE_VERTICAL_GUIDE","EXTERNAL_ROLLER","REMOTE_CONTROL","OTHER"]

def _conn():
    conn=sqlite3.connect(DB_FILE_PATH,check_same_thread=False); conn.row_factory=sqlite3.Row; return conn

def init_mooring_geometry_db():
    conn=_conn(); cur=conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_components(
    station_name TEXT NOT NULL,component_id TEXT NOT NULL,component_type TEXT NOT NULL,
    source_item INTEGER,source_piece_number TEXT,source_drawing TEXT,plan_x_px REAL,plan_y_px REAL,
    x_m REAL,y_m REAL,z_m REAL,diameter_mm REAL,notes TEXT DEFAULT '',PRIMARY KEY(station_name,component_id))""")
    existing={r[1] for r in cur.execute("PRAGMA table_info(mooring_components)")}
    for name,typ in [("source_item","INTEGER"),("source_piece_number","TEXT"),("source_drawing","TEXT")]:
        if name not in existing: cur.execute(f"ALTER TABLE mooring_components ADD COLUMN {name} {typ}")
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_connections(
    station_name TEXT NOT NULL,line_id TEXT NOT NULL,port_name TEXT,winch_id TEXT,fairlead_id TEXT,bollard_id TEXT,
    rope_diameter_mm REAL,centerline_angle_deg REAL,line_length_m REAL,geometry_status TEXT DEFAULT 'INCOMPLETE',
    PRIMARY KEY(station_name,line_id))""")
    existing={r[1] for r in cur.execute("PRAGMA table_info(mooring_connections)")}
    for name,typ in [("centerline_angle_deg","REAL"),("line_length_m","REAL"),("port_name","TEXT")]:
        if name not in existing: cur.execute(f"ALTER TABLE mooring_connections ADD COLUMN {name} {typ}")
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_route_nodes(
    station_name TEXT NOT NULL,line_id TEXT NOT NULL,sequence_no INTEGER NOT NULL,component_id TEXT NOT NULL,
    PRIMARY KEY(station_name,line_id,sequence_no))""")
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_plan_calibration(
    station_name TEXT PRIMARY KEY, drawing_width_px REAL, drawing_height_px REAL,
    rms_error_m REAL, method TEXT DEFAULT 'AFFINE_3_POINT',
    a11 REAL,a12 REAL,a13 REAL,a21 REAL,a22 REAL,a23 REAL)""")
    conn.commit(); conn.close()

def upsert_component(station_name:str,component_id:str,component_type:str,plan_x_px:Optional[float]=None,plan_y_px:Optional[float]=None,x_m:Optional[float]=None,y_m:Optional[float]=None,z_m:Optional[float]=None,diameter_mm:Optional[float]=None,notes:str="",source_item:Optional[int]=None,source_piece_number:Optional[str]=None,source_drawing:Optional[str]=None):
    init_mooring_geometry_db(); conn=_conn()
    conn.execute("""INSERT INTO mooring_components(station_name,component_id,component_type,source_item,source_piece_number,source_drawing,plan_x_px,plan_y_px,x_m,y_m,z_m,diameter_mm,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(station_name,component_id) DO UPDATE SET component_type=excluded.component_type,source_item=COALESCE(excluded.source_item,mooring_components.source_item),source_piece_number=COALESCE(excluded.source_piece_number,mooring_components.source_piece_number),source_drawing=COALESCE(excluded.source_drawing,mooring_components.source_drawing),plan_x_px=excluded.plan_x_px,plan_y_px=excluded.plan_y_px,x_m=excluded.x_m,y_m=excluded.y_m,z_m=excluded.z_m,diameter_mm=excluded.diameter_mm,notes=excluded.notes""",(station_name,component_id,component_type,source_item,source_piece_number,source_drawing,plan_x_px,plan_y_px,x_m,y_m,z_m,diameter_mm,notes)); conn.commit(); conn.close()

def seed_station_from_aft_catalog(station_name="Poppa (Aft Station)"):
    from core.mooring_station_catalog import AFT_EQUIPMENT,DRAWING_ID
    n=0
    for entry in AFT_EQUIPMENT:
        qty=int(entry.get("quantity",1)); base=str(entry["piece_number"]).replace("/","-").replace("*","X")
        for i in range(1,qty+1):
            cid=f"{base}-{i:02d}" if qty>1 else base
            upsert_component(station_name,cid,entry["type"],source_piece_number=entry.get("piece_number"),source_drawing=DRAWING_ID,notes=entry.get("description","")); n+=1
    return n

def get_components(station_name:str)->pd.DataFrame:
    init_mooring_geometry_db(); conn=_conn(); df=pd.read_sql_query("SELECT * FROM mooring_components WHERE station_name=? ORDER BY component_type,component_id",conn,params=(station_name,)); conn.close(); return df

def delete_component(station_name:str,component_id:str):
    init_mooring_geometry_db(); conn=_conn(); conn.execute("DELETE FROM mooring_components WHERE station_name=? AND component_id=?",(station_name,component_id)); conn.execute("DELETE FROM mooring_route_nodes WHERE station_name=? AND component_id=?",(station_name,component_id)); conn.execute("UPDATE mooring_connections SET winch_id=CASE WHEN winch_id=? THEN NULL ELSE winch_id END,fairlead_id=CASE WHEN fairlead_id=? THEN NULL ELSE fairlead_id END,bollard_id=CASE WHEN bollard_id=? THEN NULL ELSE bollard_id END WHERE station_name=?",(component_id,component_id,component_id,station_name)); conn.commit(); conn.close()

def upsert_connection(station_name:str,line_id:str,winch_id:str,fairlead_id:str,bollard_id:str,rope_diameter_mm:Optional[float]=None,route_nodes:Optional[Sequence[str]]=None,port_name:Optional[str]=None):
    init_mooring_geometry_db(); conn=_conn(); conn.execute("""INSERT INTO mooring_connections(station_name,line_id,port_name,winch_id,fairlead_id,bollard_id,rope_diameter_mm) VALUES(?,?,?,?,?,?,?) ON CONFLICT(station_name,line_id) DO UPDATE SET port_name=excluded.port_name,winch_id=excluded.winch_id,fairlead_id=excluded.fairlead_id,bollard_id=excluded.bollard_id,rope_diameter_mm=excluded.rope_diameter_mm""",(station_name,line_id,port_name,winch_id,fairlead_id,bollard_id,rope_diameter_mm)); conn.execute("DELETE FROM mooring_route_nodes WHERE station_name=? AND line_id=?",(station_name,line_id)); route=list(route_nodes) if route_nodes else [winch_id,fairlead_id]
    for seq,cid in enumerate(route,1): conn.execute("INSERT INTO mooring_route_nodes VALUES(?,?,?,?)",(station_name,line_id,seq,str(cid)))
    conn.commit(); conn.close(); recalculate_connection_geometry(station_name,line_id)

def get_connections(station_name:str)->pd.DataFrame:
    init_mooring_geometry_db(); conn=_conn(); df=pd.read_sql_query("SELECT * FROM mooring_connections WHERE station_name=? ORDER BY line_id",conn,params=(station_name,)); conn.close(); return df

def get_route_nodes(station_name:str,line_id:str)->list[str]:
    init_mooring_geometry_db(); conn=_conn(); rows=conn.execute("SELECT component_id FROM mooring_route_nodes WHERE station_name=? AND line_id=? ORDER BY sequence_no",(station_name,line_id)).fetchall(); conn.close(); return [str(r[0]) for r in rows]

def _point(df,cid):
    if not cid:return None
    row=df[df.component_id.astype(str)==str(cid)]
    if row.empty:return None
    r=row.iloc[0]; vals=[r.get("x_m"),r.get("y_m"),r.get("z_m")]
    if any(pd.isna(v) for v in vals):return None
    return tuple(float(v) for v in vals)

def _bollard_point(port_name,bollard_id):
    if not port_name or not bollard_id:return None
    conn=_conn(); row=conn.execute("SELECT x_m,y_m,z_m FROM port_bollards WHERE port_name=? AND bollard_id=?",(port_name,bollard_id)).fetchone(); conn.close()
    if row is None or any(v is None for v in row):return None
    return tuple(float(v) for v in row)

def _angle_between(a,b):
    na=math.sqrt(sum(v*v for v in a)); nb=math.sqrt(sum(v*v for v in b))
    if na==0 or nb==0:return None
    return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))/(na*nb)))))

def route_geometry(station_name,line_id):
    comps=get_components(station_name); rows=get_connections(station_name); rows=rows[rows.line_id.astype(str)==str(line_id)]
    if rows.empty:return {}
    r=rows.iloc[0]; nodes=get_route_nodes(station_name,line_id) or [str(r.get("winch_id")),str(r.get("fairlead_id"))]
    points=[]; labels=[]; missing=[]
    for cid in nodes:
        p=_point(comps,cid)
        if p is None:missing.append(cid)
        else:points.append(p); labels.append(cid)
    b=_bollard_point(r.get("port_name"),r.get("bollard_id"))
    if b is None: missing.append(f"BOLLARD:{r.get('bollard_id')}")
    else: points.append(b); labels.append(f"BOLLARD:{r.get('bollard_id')}")
    length=None; segments=[]
    if len(points)==len(labels) and len(points)>=2 and not missing:
        segments=[math.dist(a,b) for a,b in zip(points,points[1:])]; length=sum(segments)
    changes=[]
    if length is not None:
        for i in range(1,len(points)-1):
            a,c,bp=points[i-1],points[i],points[i+1]
            changes.append({"component_id":labels[i],"angle_deg":_angle_between(tuple(a[j]-c[j] for j in range(3)),tuple(bp[j]-c[j] for j in range(3)))})
    return {"line_id":line_id,"nodes":labels,"segment_lengths_m":segments,"line_length_m":length,"direction_changes":changes,"missing_coordinates":missing,"status":"COMPLETE" if length is not None else "INCOMPLETE"}

def recalculate_connection_geometry(station_name,line_id):
    rows=get_connections(station_name); rows=rows[rows.line_id.astype(str)==str(line_id)]
    if rows.empty:return
    r=rows.iloc[0]; geo=route_geometry(station_name,line_id); changes=geo.get("direction_changes",[]); angle=changes[0]["angle_deg"] if changes else None
    status="COMPLETE" if geo.get("status")=="COMPLETE" else "INCOMPLETE"
    conn=_conn(); conn.execute("UPDATE mooring_connections SET centerline_angle_deg=?,line_length_m=?,geometry_status=? WHERE station_name=? AND line_id=?",(angle,geo.get("line_length_m"),status,station_name,line_id)); conn.commit(); conn.close()

def recalculate_all(station_name):
    for line_id in get_connections(station_name).get("line_id",pd.Series(dtype=str)).astype(str):recalculate_connection_geometry(station_name,line_id)

def get_line_detail(station_name,line_id):
    comps,conns=get_components(station_name),get_connections(station_name); row=conns[conns.line_id.astype(str)==str(line_id)]
    if row.empty:return {}
    r=row.iloc[0].to_dict(); return {"line_id":line_id,**r,"route_nodes":get_route_nodes(station_name,line_id),"derived_geometry":route_geometry(station_name,line_id)}
