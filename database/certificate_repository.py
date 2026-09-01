"""Traceable repository for reviewed mooring certificates.

Kept separate from the legacy certificate table while the database schema is
being migrated. This table stores certificate-derived engineering data,
provenance and operator review status without changing the existing schema.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from config.constants import DB_FILE_PATH


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_certificate_repository() -> None:
    conn = _connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS certificate_records (
            cert_id TEXT PRIMARY KEY,
            certificate_type TEXT NOT NULL,
            manufacturer TEXT NOT NULL,
            material_grade TEXT NOT NULL,
            diameter_mm REAL NOT NULL,
            length_m REAL NOT NULL,
            ship_design_mbl_t REAL,
            ldbf_t REAL,
            tail_tdbf_t REAL,
            tail_length_m REAL,
            standard_basis TEXT,
            issue_date TEXT,
            strain_json TEXT,
            source_text TEXT,
            extraction_method TEXT,
            review_status TEXT NOT NULL,
            reviewed_at TEXT,
            notes TEXT DEFAULT ''
        )
    """)
    conn.commit()
    conn.close()


def save_reviewed_certificate(record: dict[str, Any]) -> None:
    init_certificate_repository()
    required = ["cert_id", "certificate_type", "manufacturer", "material_grade", "diameter_mm", "length_m", "review_status"]
    missing = [key for key in required if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Missing certificate fields: {', '.join(missing)}")
    if float(record["diameter_mm"]) <= 0 or float(record["length_m"]) <= 0:
        raise ValueError("Certificate diameter and length must be greater than zero.")
    if record["review_status"] not in {"OPERATOR_VERIFIED", "REVIEW_REQUIRED", "REJECTED"}:
        raise ValueError("Invalid certificate review status.")

    conn = _connection()
    conn.execute("""
        INSERT OR REPLACE INTO certificate_records (
            cert_id, certificate_type, manufacturer, material_grade,
            diameter_mm, length_m, ship_design_mbl_t, ldbf_t, tail_tdbf_t,
            tail_length_m, standard_basis, issue_date, strain_json,
            source_text, extraction_method, review_status, reviewed_at, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(record["cert_id"]).strip(),
        str(record["certificate_type"]).strip(),
        str(record["manufacturer"]).strip(),
        str(record["material_grade"]).strip(),
        float(record["diameter_mm"]),
        float(record["length_m"]),
        record.get("ship_design_mbl_t"),
        record.get("ldbf_t"),
        record.get("tail_tdbf_t"),
        record.get("tail_length_m"),
        str(record.get("standard_basis", "")).strip(),
        str(record.get("issue_date", "")).strip(),
        json.dumps(record.get("strain", {}), sort_keys=True),
        str(record.get("source_text", "")),
        str(record.get("extraction_method", "")),
        str(record["review_status"]),
        datetime.utcnow().isoformat(timespec="seconds") if record["review_status"] == "OPERATOR_VERIFIED" else None,
        str(record.get("notes", "")),
    ))
    conn.commit()
    conn.close()


def load_certificate_records():
    init_certificate_repository()
    conn = _connection()
    rows = conn.execute("SELECT * FROM certificate_records ORDER BY cert_id").fetchall()
    conn.close()
    return [dict(row) for row in rows]
