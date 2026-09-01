"""SQLite persistence for mooring sessions and time-series snapshots."""
from __future__ import annotations
import sqlite3
from config.constants import DB_FILE_PATH
from core.mooring_session import MooringSession, EnvironmentalObservation, LineExposure

def _conn():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_session_schema() -> None:
    conn = _conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_sessions (
        session_id TEXT PRIMARY KEY, port_name TEXT NOT NULL, berth_name TEXT,
        start_utc TEXT NOT NULL, end_utc TEXT, status TEXT NOT NULL,
        notes TEXT DEFAULT ''
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS session_environment (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL, wind_speed_mps REAL, wind_direction_deg REAL,
        gust_mps REAL, current_speed_mps REAL, current_direction_deg REAL,
        wave_height_m REAL, wave_period_s REAL, provider TEXT NOT NULL,
        source_kind TEXT NOT NULL, FOREIGN KEY(session_id) REFERENCES mooring_sessions(session_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS session_line_exposure (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        line_id TEXT NOT NULL, timestamp_utc TEXT NOT NULL, tension_n REAL NOT NULL,
        mbl_n REAL NOT NULL, utilization_pct REAL NOT NULL, duration_s REAL NOT NULL,
        source TEXT NOT NULL, FOREIGN KEY(session_id) REFERENCES mooring_sessions(session_id)
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_env ON session_environment(session_id, timestamp_utc)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_line ON session_line_exposure(line_id, timestamp_utc)")
    conn.commit(); conn.close()

def create_session(session: MooringSession) -> None:
    init_session_schema(); conn = _conn()
    conn.execute("INSERT INTO mooring_sessions(session_id,port_name,berth_name,start_utc,end_utc,status,notes) VALUES (?,?,?,?,?,?,?)",
                 (session.session_id, session.port_name, session.berth_name, session.start_utc, session.end_utc, session.status, session.notes))
    conn.commit(); conn.close()

def add_environment(session_id: str, obs: EnvironmentalObservation) -> None:
    init_session_schema(); conn = _conn()
    conn.execute("""INSERT INTO session_environment(session_id,timestamp_utc,wind_speed_mps,wind_direction_deg,gust_mps,current_speed_mps,current_direction_deg,wave_height_m,wave_period_s,provider,source_kind)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                 (session_id, obs.timestamp_utc, obs.wind_speed_mps, obs.wind_direction_deg, obs.gust_mps, obs.current_speed_mps, obs.current_direction_deg, obs.wave_height_m, obs.wave_period_s, obs.provider, obs.source_kind))
    conn.commit(); conn.close()

def add_line_exposure(session_id: str, exposure: LineExposure) -> None:
    init_session_schema(); conn = _conn()
    conn.execute("""INSERT INTO session_line_exposure(session_id,line_id,timestamp_utc,tension_n,mbl_n,utilization_pct,duration_s,source)
                    VALUES (?,?,?,?,?,?,?,?)""",
                 (session_id, exposure.line_id, exposure.timestamp_utc, exposure.tension_n, exposure.mbl_n, exposure.utilization_pct, exposure.duration_s, exposure.source))
    conn.commit(); conn.close()

def complete_session(session_id: str, end_utc: str) -> None:
    init_session_schema(); conn = _conn()
    cur = conn.execute("UPDATE mooring_sessions SET end_utc=?, status='COMPLETED' WHERE session_id=? AND status='ACTIVE'", (end_utc, session_id))
    if cur.rowcount != 1:
        conn.close(); raise ValueError("Active mooring session not found")
    conn.commit(); conn.close()
