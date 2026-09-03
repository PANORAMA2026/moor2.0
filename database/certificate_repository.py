"""Traceable repository for reviewed mooring certificates and source PDFs.

Certificate-derived engineering data remains separate from the legacy table.
The original PDF is retained as a BLOB with SHA-256 provenance. Extracted
values are never treated as verified until the operator explicitly reviews them.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
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
            notes TEXT DEFAULT '',
            source_pdf_filename TEXT DEFAULT '',
            source_pdf_sha256 TEXT DEFAULT '',
            source_pdf_blob BLOB
        )
    """)
    # Migration for databases created before PDF provenance was introduced.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(certificate_records)").fetchall()}
    for name, sql in {
        "source_pdf_filename": "ALTER TABLE certificate_records ADD COLUMN source_pdf_filename TEXT DEFAULT ''",
        "source_pdf_sha256": "ALTER TABLE certificate_records ADD COLUMN source_pdf_sha256 TEXT DEFAULT ''",
        "source_pdf_blob": "ALTER TABLE certificate_records ADD COLUMN source_pdf_blob BLOB",
    }.items():
        if name not in existing:
            conn.execute(sql)
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

    pdf_bytes = record.get("source_pdf_bytes")
    if pdf_bytes:
        if not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF"):
            raise ValueError("source_pdf_bytes must contain a valid PDF document.")
        pdf_bytes = bytes(pdf_bytes)
        pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    else:
        pdf_sha256 = str(record.get("source_pdf_sha256", ""))

    conn = _connection()
    conn.execute("""
        INSERT OR REPLACE INTO certificate_records (
            cert_id, certificate_type, manufacturer, material_grade,
            diameter_mm, length_m, ship_design_mbl_t, ldbf_t, tail_tdbf_t,
            tail_length_m, standard_basis, issue_date, strain_json,
            source_text, extraction_method, review_status, reviewed_at, notes,
            source_pdf_filename, source_pdf_sha256, source_pdf_blob
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        str(record["cert_id"]).strip(), str(record["certificate_type"]).strip(),
        str(record["manufacturer"]).strip(), str(record["material_grade"]).strip(),
        float(record["diameter_mm"]), float(record["length_m"]),
        record.get("ship_design_mbl_t"), record.get("ldbf_t"), record.get("tail_tdbf_t"),
        record.get("tail_length_m"), str(record.get("standard_basis", "")).strip(),
        str(record.get("issue_date", "")).strip(), json.dumps(record.get("strain", {}), sort_keys=True),
        str(record.get("source_text", "")), str(record.get("extraction_method", "")),
        str(record["review_status"]), datetime.now(timezone.utc).isoformat(timespec="seconds") if record["review_status"] == "OPERATOR_VERIFIED" else None,
        str(record.get("notes", "")), str(record.get("source_pdf_filename", "")), pdf_sha256, pdf_bytes,
    ))
    conn.commit()
    conn.close()


def load_certificate_records():
    init_certificate_repository()
    conn = _connection()
    rows = conn.execute("""
        SELECT cert_id, certificate_type, manufacturer, material_grade,
               diameter_mm, length_m, ship_design_mbl_t, ldbf_t, tail_tdbf_t,
               tail_length_m, standard_basis, issue_date, strain_json,
               extraction_method, review_status, reviewed_at, notes,
               source_pdf_filename, source_pdf_sha256,
               CASE WHEN source_pdf_blob IS NULL THEN 0 ELSE 1 END AS pdf_stored
        FROM certificate_records ORDER BY cert_id
    """).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_certificate_pdf(cert_id: str) -> dict[str, Any] | None:
    init_certificate_repository()
    conn = _connection()
    row = conn.execute(
        "SELECT cert_id, source_pdf_filename, source_pdf_sha256, source_pdf_blob FROM certificate_records WHERE cert_id = ?",
        (str(cert_id).strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
