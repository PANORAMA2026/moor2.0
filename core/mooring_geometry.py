"""Canonical geometry/configuration layer for the interactive mooring plan."""

import math
import sqlite3
from typing import Optional

import pandas as pd

from config.constants import DB_FILE_PATH

COMPONENT_TYPES = [
    "WINCH", "FAIRLEAD", "CHOCK", "CAPSTAN", "BOLLARD",
    "VERTICAL_GUIDE", "DOUBLE_VERTICAL_GUIDE", "EXTERNAL_ROLLER",
    "REMOTE_CONTROL", "OTHER",
]


def _conn():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_mooring_geometry_db():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mooring_components (
            station_name TEXT NOT NULL,
            component_id TEXT NOT NULL,
            component_type TEXT NOT NULL,
            source_item INTEGER,
            source_piece_number TEXT,
            source_drawing TEXT,
            plan_x_px REAL,
            plan_y_px REAL,
            x_m REAL,
            y_m REAL,
            z_m REAL,
            diameter_mm REAL,
            notes TEXT DEFAULT '',
            PRIMARY KEY (station_name, component_id)
        )
    """)
    existing = {r[1] for r in cur.execute("PRAGMA table_info(mooring_components)").fetchall()}
    for name, sql_type in [("source_item", "INTEGER"), ("source_piece_number", "TEXT"), ("source_drawing", "TEXT")]:
        if name not in existing:
            cur.execute(f"ALTER TABLE mooring_components ADD COLUMN {name} {sql_type}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mooring_connections (
            station_name TEXT NOT NULL,
            line_id TEXT NOT NULL,
            winch_id TEXT,
            fairlead_id TEXT,
            bollard_id TEXT,
            rope_diameter_mm REAL,
            centerline_angle_deg REAL,
            contact_angle_deg REAL,
            wrap_angle_deg REAL,
            geometry_status TEXT DEFAULT 'INCOMPLETE',
            PRIMARY KEY (station_name, line_id)
        )
    """)
    existing_conn = {r[1] for r in cur.execute("PRAGMA table_info(mooring_connections)").fetchall()}
    if "centerline_angle_deg" not in existing_conn:
        cur.execute("ALTER TABLE mooring_connections ADD COLUMN centerline_angle_deg REAL")
    conn.commit()
    conn.close()


def upsert_component(station_name: str, component_id: str, component_type: str,
                     plan_x_px: Optional[float] = None, plan_y_px: Optional[float] = None,
                     x_m: Optional[float] = None, y_m: Optional[float] = None,
                     z_m: Optional[float] = None, diameter_mm: Optional[float] = None,
                     notes: str = "", source_item: Optional[int] = None,
                     source_piece_number: Optional[str] = None,
                     source_drawing: Optional[str] = None):
    init_mooring_geometry_db()
    conn = _conn()
    conn.execute("""
        INSERT INTO mooring_components (
            station_name, component_id, component_type, source_item,
            source_piece_number, source_drawing, plan_x_px, plan_y_px,
            x_m, y_m, z_m, diameter_mm, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(station_name, component_id) DO UPDATE SET
            component_type=excluded.component_type,
            source_item=COALESCE(excluded.source_item, mooring_components.source_item),
            source_piece_number=COALESCE(excluded.source_piece_number, mooring_components.source_piece_number),
            source_drawing=COALESCE(excluded.source_drawing, mooring_components.source_drawing),
            plan_x_px=excluded.plan_x_px, plan_y_px=excluded.plan_y_px,
            x_m=excluded.x_m, y_m=excluded.y_m, z_m=excluded.z_m,
            diameter_mm=excluded.diameter_mm, notes=excluded.notes
    """, (station_name, component_id, component_type, source_item, source_piece_number,
          source_drawing, plan_x_px, plan_y_px, x_m, y_m, z_m, diameter_mm, notes))
    conn.commit()
    conn.close()


def seed_station_from_aft_catalog(station_name: str = "Poppa (Aft Station)") -> int:
    """Seed source-identified AFT equipment; never invent plan/ship coordinates."""
    from core.mooring_station_catalog import AFT_EQUIPMENT, DRAWING_ID
    created = 0
    for entry in AFT_EQUIPMENT:
        qty = int(entry.get("quantity", 1))
        for idx in range(1, qty + 1):
            base = str(entry["piece_number"]).replace("/", "-").replace("*", "X")
            suffix = f"-{idx:02d}" if qty > 1 else ""
            upsert_component(
                station_name, f"{base}{suffix}", entry["type"],
                source_item=entry.get("item"), source_piece_number=entry.get("piece_number"),
                source_drawing=DRAWING_ID, notes=entry.get("description", ""),
            )
            created += 1
    return created


def get_components(station_name: str) -> pd.DataFrame:
    init_mooring_geometry_db()
    conn = _conn()
    df = pd.read_sql_query(
        "SELECT * FROM mooring_components WHERE station_name = ? ORDER BY component_type, component_id",
        conn, params=(station_name,))
    conn.close()
    return df


def delete_component(station_name: str, component_id: str):
    init_mooring_geometry_db()
    conn = _conn()
    conn.execute("DELETE FROM mooring_components WHERE station_name=? AND component_id=?", (station_name, component_id))
    conn.execute("""
        UPDATE mooring_connections
        SET winch_id=CASE WHEN winch_id=? THEN NULL ELSE winch_id END,
            fairlead_id=CASE WHEN fairlead_id=? THEN NULL ELSE fairlead_id END,
            bollard_id=CASE WHEN bollard_id=? THEN NULL ELSE bollard_id END
        WHERE station_name=?
    """, (component_id, component_id, component_id, station_name))
    conn.commit()
    conn.close()


def upsert_connection(station_name: str, line_id: str, winch_id: str, fairlead_id: str,
                      bollard_id: str, rope_diameter_mm: Optional[float] = None):
    init_mooring_geometry_db()
    conn = _conn()
    conn.execute("""
        INSERT INTO mooring_connections (station_name,line_id,winch_id,fairlead_id,bollard_id,rope_diameter_mm)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(station_name,line_id) DO UPDATE SET
            winch_id=excluded.winch_id, fairlead_id=excluded.fairlead_id,
            bollard_id=excluded.bollard_id, rope_diameter_mm=excluded.rope_diameter_mm
    """, (station_name, line_id, winch_id, fairlead_id, bollard_id, rope_diameter_mm))
    conn.commit()
    conn.close()
    recalculate_connection_geometry(station_name, line_id)


def get_connections(station_name: str) -> pd.DataFrame:
    init_mooring_geometry_db()
    conn = _conn()
    df = pd.read_sql_query("SELECT * FROM mooring_connections WHERE station_name=? ORDER BY line_id", conn, params=(station_name,))
    conn.close()
    return df


def _point(df: pd.DataFrame, component_id: str):
    if not component_id:
        return None
    row = df[df["component_id"].astype(str) == str(component_id)]
    if row.empty:
        return None
    r = row.iloc[0]
    vals = [r.get("x_m"), r.get("y_m"), r.get("z_m")]
    if any(pd.isna(v) for v in vals):
        return None
    return tuple(float(v) for v in vals)


def _angle_between(a, b):
    na = math.sqrt(sum(v*v for v in a)); nb = math.sqrt(sum(v*v for v in b))
    if na == 0 or nb == 0:
        return None
    c = max(-1.0, min(1.0, sum(x*y for x,y in zip(a,b))/(na*nb)))
    return math.degrees(math.acos(c))


def recalculate_connection_geometry(station_name: str, line_id: str):
    components = get_components(station_name)
    rows = get_connections(station_name)
    rows = rows[rows["line_id"].astype(str) == str(line_id)]
    if rows.empty:
        return
    r = rows.iloc[0]
    w, f, b = _point(components, r.get("winch_id")), _point(components, r.get("fairlead_id")), _point(components, r.get("bollard_id"))
    angle = None; status = "INCOMPLETE"
    if w and f and b:
        angle = _angle_between(tuple(w[i]-f[i] for i in range(3)), tuple(b[i]-f[i] for i in range(3)))
        status = "CENTERLINE_ANGLE_ONLY"
    conn = _conn()
    conn.execute("""
        UPDATE mooring_connections
        SET centerline_angle_deg=?, contact_angle_deg=NULL, wrap_angle_deg=NULL, geometry_status=?
        WHERE station_name=? AND line_id=?
    """, (angle, status, station_name, line_id))
    conn.commit(); conn.close()


def recalculate_all(station_name: str):
    for line_id in get_connections(station_name).get("line_id", pd.Series(dtype=str)).astype(str):
        recalculate_connection_geometry(station_name, line_id)


def get_line_detail(station_name: str, line_id: str) -> dict:
    components, connections = get_components(station_name), get_connections(station_name)
    row = connections[connections["line_id"].astype(str) == str(line_id)]
    if row.empty:
        return {}
    r = row.iloc[0].to_dict(); result = {"line_id": line_id, **r}
    for key, label in [("winch_id","Winch"),("fairlead_id","Fairlead"),("bollard_id","Bollard")]:
        cid = r.get(key); result[label] = cid
        if cid:
            c = components[components["component_id"].astype(str) == str(cid)]
            if not c.empty:
                result[f"{label}_x_m"] = c.iloc[0].get("x_m")
                result[f"{label}_y_m"] = c.iloc[0].get("y_m")
                result[f"{label}_z_m"] = c.iloc[0].get("z_m")
                result[f"{label}_diameter_mm"] = c.iloc[0].get("diameter_mm")
    return result
