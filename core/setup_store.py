"""Persistent editable mooring setup topology.

The existing port_mooring_setups table stores pretension/MBL percentages only.
This module adds a separate topology store for the operational connection:
winch -> fairlead -> line -> bollard.  It deliberately does not alter solver
physics and keeps saved alternatives separate from the reference normal setup.
"""
from __future__ import annotations

import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from config.constants import DB_FILE_PATH
from core.mooring_setup_profiles import get_normal_setup


TABLE = "mooring_setup_connections"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_setup_store() -> None:
    conn = _connect()
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {TABLE} (
            port_name TEXT NOT NULL,
            setup_name TEXT NOT NULL,
            line_id TEXT NOT NULL,
            station TEXT NOT NULL,
            line_type TEXT NOT NULL,
            winch_id TEXT,
            fairlead_id TEXT NOT NULL,
            bollard_id TEXT NOT NULL,
            bollard_station TEXT NOT NULL,
            side TEXT NOT NULL DEFAULT 'PORT',
            source TEXT NOT NULL DEFAULT 'OPERATOR',
            updated_utc TEXT NOT NULL,
            PRIMARY KEY (port_name, setup_name, line_id)
        )"""
    )
    conn.commit()
    conn.close()


def _normal_records(port_name: str) -> list[dict]:
    return [
        {
            "port_name": port_name,
            "setup_name": "Normal",
            "line_id": c.line_id,
            "station": c.station,
            "line_type": c.line_type,
            "winch_id": None,
            "fairlead_id": c.fairlead_id,
            "bollard_id": c.bollard_id,
            "bollard_station": c.bollard_station,
            "side": c.side,
            "source": "REFERENCE",
            "updated_utc": datetime.now(timezone.utc).isoformat(),
        }
        for c in get_normal_setup()
    ]


def ensure_normal_setup(port_name: str = "Ensenada Pier #2") -> None:
    init_setup_store()
    conn = _connect()
    count = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE port_name=? AND setup_name=?",
        (port_name, "Normal"),
    ).fetchone()[0]
    if count == 0:
        conn.executemany(
            f"""INSERT INTO {TABLE}
            (port_name,setup_name,line_id,station,line_type,winch_id,fairlead_id,
             bollard_id,bollard_station,side,source,updated_utc)
            VALUES (:port_name,:setup_name,:line_id,:station,:line_type,:winch_id,
                    :fairlead_id,:bollard_id,:bollard_station,:side,:source,:updated_utc)""",
            _normal_records(port_name),
        )
        conn.commit()
    conn.close()


def list_setup_names(port_name: str = "Ensenada Pier #2") -> list[str]:
    ensure_normal_setup(port_name)
    conn = _connect()
    rows = conn.execute(
        f"SELECT DISTINCT setup_name FROM {TABLE} WHERE port_name=? ORDER BY setup_name",
        (port_name,),
    ).fetchall()
    conn.close()
    return [str(r[0]) for r in rows]


def load_setup(port_name: str, setup_name: str = "Normal") -> pd.DataFrame:
    ensure_normal_setup(port_name)
    conn = _connect()
    df = pd.read_sql_query(
        f"SELECT * FROM {TABLE} WHERE port_name=? AND setup_name=? ORDER BY station,line_id",
        conn,
        params=(port_name, setup_name),
    )
    conn.close()
    return df


def save_setup(port_name: str, setup_name: str, df: pd.DataFrame, source: str = "OPERATOR") -> None:
    setup_name = str(setup_name).strip()
    if not setup_name:
        raise ValueError("Setup name cannot be empty")
    required = [
        "line_id", "station", "line_type", "winch_id", "fairlead_id",
        "bollard_id", "bollard_station", "side",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing setup columns: {', '.join(missing)}")

    init_setup_store()
    conn = _connect()
    conn.execute(
        f"DELETE FROM {TABLE} WHERE port_name=? AND setup_name=?",
        (port_name, setup_name),
    )
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for _, row in df.iterrows():
        records.append({
            "port_name": port_name,
            "setup_name": setup_name,
            "line_id": str(row["line_id"]),
            "station": str(row["station"]),
            "line_type": str(row["line_type"]),
            "winch_id": None if pd.isna(row["winch_id"]) else str(row["winch_id"]),
            "fairlead_id": str(row["fairlead_id"]),
            "bollard_id": str(row["bollard_id"]),
            "bollard_station": str(row["bollard_station"]),
            "side": str(row["side"]),
            "source": source,
            "updated_utc": now,
        })
    conn.executemany(
        f"""INSERT INTO {TABLE}
        (port_name,setup_name,line_id,station,line_type,winch_id,fairlead_id,
         bollard_id,bollard_station,side,source,updated_utc)
        VALUES (:port_name,:setup_name,:line_id,:station,:line_type,:winch_id,
                :fairlead_id,:bollard_id,:bollard_station,:side,:source,:updated_utc)""",
        records,
    )
    conn.commit()
    conn.close()


def delete_setup(port_name: str, setup_name: str) -> None:
    if setup_name == "Normal":
        raise ValueError("The Normal reference setup cannot be deleted")
    init_setup_store()
    conn = _connect()
    conn.execute(
        f"DELETE FROM {TABLE} WHERE port_name=? AND setup_name=?",
        (port_name, setup_name),
    )
    conn.commit()
    conn.close()


def validate_setup(df: pd.DataFrame, fairlead_ids: set[str], bollard_keys: set[tuple[str, str]]) -> list[str]:
    errors: list[str] = []
    if df.empty:
        return ["Setup is empty"]
    if df["line_id"].duplicated().any():
        errors.append("Duplicate line_id detected")
    for _, row in df.iterrows():
        line = str(row["line_id"])
        fl = str(row["fairlead_id"])
        bk = (str(row["bollard_station"]).upper(), str(row["bollard_id"]).upper())
        if fl not in fairlead_ids:
            errors.append(f"{line}: fairlead {fl} does not exist")
        if bk not in bollard_keys:
            errors.append(f"{line}: bollard {bk[1]} ({bk[0]}) does not exist")
        if str(row["station"]).upper() not in {"FWD", "AFT"}:
            errors.append(f"{line}: invalid station")
    return errors
