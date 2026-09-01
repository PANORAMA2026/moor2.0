"""SQLite persistence for schedule-driven mooring sessions."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from config.constants import DB_FILE_PATH
from core.mooring_session import MooringSession, EnvironmentalObservation, LineExposure, SessionStatus


def _conn():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_session_schema() -> None:
    conn = _conn(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS mooring_sessions (
        session_id TEXT PRIMARY KEY, port_name TEXT NOT NULL, berth_name TEXT,
        start_utc TEXT, end_utc TEXT, status TEXT NOT NULL, notes TEXT DEFAULT '',
        schedule_id TEXT, schedule_fingerprint TEXT, setup_name TEXT,
        setup_source TEXT DEFAULT 'SCHEDULE', scheduled_start_utc TEXT,
        scheduled_end_utc TEXT, created_at_utc TEXT, updated_at_utc TEXT
    )""")
    existing = {r[1] for r in cur.execute("PRAGMA table_info(mooring_sessions)").fetchall()}
    for name, sql_type in {
        "schedule_id": "TEXT", "schedule_fingerprint": "TEXT", "setup_name": "TEXT",
        "setup_source": "TEXT DEFAULT 'SCHEDULE'", "scheduled_start_utc": "TEXT",
        "scheduled_end_utc": "TEXT", "created_at_utc": "TEXT", "updated_at_utc": "TEXT",
    }.items():
        if name not in existing:
            cur.execute(f"ALTER TABLE mooring_sessions ADD COLUMN {name} {sql_type}")
    cur.execute("""CREATE TABLE IF NOT EXISTS session_environment (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        timestamp_utc TEXT NOT NULL, wind_speed_mps REAL, wind_direction_deg REAL,
        gust_mps REAL, current_speed_mps REAL, current_direction_deg REAL,
        wave_height_m REAL, wave_period_s REAL, provider TEXT NOT NULL,
        source_kind TEXT NOT NULL, forecast_reference_time TEXT,
        tidal_current_u_mps REAL, tidal_current_v_mps REAL,
        water_level_m REAL, water_level_datum TEXT
    )""")
    env_cols = {r[1] for r in cur.execute("PRAGMA table_info(session_environment)").fetchall()}
    for name, sql_type in {
        "tidal_current_u_mps": "REAL", "tidal_current_v_mps": "REAL",
        "water_level_m": "REAL", "water_level_datum": "TEXT",
    }.items():
        if name not in env_cols:
            cur.execute(f"ALTER TABLE session_environment ADD COLUMN {name} {sql_type}")
    cur.execute("""CREATE TABLE IF NOT EXISTS session_line_exposure (
        id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
        line_id TEXT NOT NULL, timestamp_utc TEXT NOT NULL, tension_n REAL,
        mbl_n REAL, utilization_pct REAL, duration_s REAL NOT NULL,
        source TEXT NOT NULL, valid INTEGER DEFAULT 1, diagnostic TEXT DEFAULT ''
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_env ON session_environment(session_id, timestamp_utc)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_session_line ON session_line_exposure(line_id, timestamp_utc)")
    conn.commit(); conn.close()


def save_session(session: MooringSession) -> None:
    init_session_schema(); conn = _conn(); now = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO mooring_sessions(
        session_id,port_name,berth_name,start_utc,end_utc,status,notes,
        schedule_id,schedule_fingerprint,setup_name,setup_source,
        scheduled_start_utc,scheduled_end_utc,created_at_utc,updated_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(session_id) DO UPDATE SET
        port_name=excluded.port_name, berth_name=excluded.berth_name,
        start_utc=excluded.start_utc, end_utc=excluded.end_utc,
        status=excluded.status, notes=excluded.notes,
        schedule_id=excluded.schedule_id, schedule_fingerprint=excluded.schedule_fingerprint,
        setup_name=excluded.setup_name, setup_source=excluded.setup_source,
        scheduled_start_utc=excluded.scheduled_start_utc,
        scheduled_end_utc=excluded.scheduled_end_utc, updated_at_utc=excluded.updated_at_utc""",
        (session.session_id,session.port_name,session.berth_name,session.start_utc,session.end_utc,
         session.status.value,session.notes,session.schedule_id,session.schedule_fingerprint,
         session.setup_name,session.setup_source,session.scheduled_start_utc,session.scheduled_end_utc,now,now))
    conn.commit(); conn.close()


def create_session(session: MooringSession) -> None:
    save_session(session)


def load_by_session_id(session_id: str) -> MooringSession | None:
    init_session_schema(); conn = _conn()
    row = conn.execute("SELECT * FROM mooring_sessions WHERE session_id=?", (session_id,)).fetchone(); conn.close()
    if row is None: return None
    return MooringSession(session_id=row["session_id"],port_name=row["port_name"],berth_name=row["berth_name"],
        start_utc=row["start_utc"],scheduled_start_utc=row["scheduled_start_utc"],scheduled_end_utc=row["scheduled_end_utc"],
        end_utc=row["end_utc"],status=SessionStatus(row["status"]),schedule_id=row["schedule_id"],setup_name=row["setup_name"],
        setup_source=row["setup_source"] or "SCHEDULE",schedule_fingerprint=row["schedule_fingerprint"],notes=row["notes"] or "")


def load_active_or_scheduled() -> list[MooringSession]:
    init_session_schema(); conn = _conn()
    rows = conn.execute("SELECT session_id FROM mooring_sessions WHERE status IN ('SCHEDULED','ACTIVE') ORDER BY scheduled_start_utc").fetchall(); conn.close()
    return [s for s in (load_by_session_id(r["session_id"]) for r in rows) if s is not None]


def add_environment(session_id: str, obs: EnvironmentalObservation) -> None:
    init_session_schema(); conn = _conn()
    conn.execute("""INSERT INTO session_environment(
        session_id,timestamp_utc,wind_speed_mps,wind_direction_deg,gust_mps,
        current_speed_mps,current_direction_deg,wave_height_m,wave_period_s,
        provider,source_kind,forecast_reference_time,tidal_current_u_mps,
        tidal_current_v_mps,water_level_m,water_level_datum)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (session_id,obs.timestamp_utc,obs.wind_speed_mps,obs.wind_direction_deg,obs.gust_mps,
         obs.current_speed_mps,obs.current_direction_deg,obs.wave_height_m,obs.wave_period_s,
         obs.provider,obs.source_kind,obs.forecast_reference_time,obs.tidal_current_u_mps,
         obs.tidal_current_v_mps,obs.water_level_m,obs.water_level_datum)); conn.commit(); conn.close()


def add_line_exposure(session_id: str, exposure: LineExposure) -> None:
    init_session_schema(); conn = _conn()
    conn.execute("INSERT INTO session_line_exposure(session_id,line_id,timestamp_utc,tension_n,mbl_n,utilization_pct,duration_s,source,valid,diagnostic) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (session_id,exposure.line_id,exposure.timestamp_utc,exposure.tension_n,exposure.mbl_n,exposure.utilization_pct,exposure.duration_s,exposure.source,1 if exposure.valid else 0,exposure.diagnostic)); conn.commit(); conn.close()


def complete_session(session_id: str, end_utc: str) -> None:
    init_session_schema(); conn = _conn()
    cur = conn.execute("UPDATE mooring_sessions SET end_utc=?,status='COMPLETED',updated_at_utc=? WHERE session_id=? AND status='ACTIVE'", (end_utc,datetime.now(timezone.utc).isoformat(),session_id))
    if cur.rowcount != 1: conn.close(); raise ValueError("Active mooring session not found")
    conn.commit(); conn.close()
