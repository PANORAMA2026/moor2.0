"""AI-assisted visual inspection of mooring lines.

The AI layer is deliberately advisory. It classifies visible damage and image
quality, but it never invents wear percentages, residual strength, retirement
criteria, or an operational acceptance decision. Every assessment remains
pending operator confirmation.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

import streamlit as st

from config.constants import DB_FILE_PATH

MODEL_DEFAULT = "gpt-5.6-luna"
DAMAGE_TYPES = (
    "abrasion",
    "glazing_or_heat_damage",
    "broken_yarns_or_strands",
    "cut_or_severed_fibres",
    "chemical_or_contamination",
    "deformation_or_flattening",
    "sheath_or_cover_damage",
    "splice_or_end_damage",
    "unknown",
)
SEVERITIES = ("NONE", "LOW", "MODERATE", "HIGH", "CRITICAL", "UNDETERMINED")


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def ai_is_configured() -> bool:
    return bool(_secret("OPENAI_API_KEY"))


def init_ai_repository() -> None:
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS ai_line_inspections (
            inspection_id TEXT PRIMARY KEY,
            line_id TEXT NOT NULL,
            timestamp_utc TEXT NOT NULL,
            model TEXT NOT NULL,
            image_sha256 TEXT NOT NULL,
            image_mime TEXT NOT NULL,
            image_blob BLOB NOT NULL,
            image_quality TEXT NOT NULL,
            overall_severity TEXT NOT NULL,
            confidence REAL,
            findings_json TEXT NOT NULL,
            ai_summary TEXT NOT NULL,
            retake_requested INTEGER NOT NULL DEFAULT 0,
            operator_status TEXT NOT NULL DEFAULT 'PENDING_OPERATOR_CONFIRMATION',
            operator_note TEXT DEFAULT '',
            confirmed_at_utc TEXT
        )"""
    )
    conn.commit()
    conn.close()


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def _normalize(result: dict[str, Any]) -> dict[str, Any]:
    quality = str(result.get("image_quality", "UNDETERMINED")).upper()
    if quality not in {"GOOD", "ACCEPTABLE", "POOR", "INSUFFICIENT", "UNDETERMINED"}:
        quality = "UNDETERMINED"
    severity = str(result.get("overall_severity", "UNDETERMINED")).upper()
    if severity not in SEVERITIES:
        severity = "UNDETERMINED"
    confidence = result.get("confidence")
    try:
        confidence = max(0.0, min(1.0, float(confidence))) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    findings = []
    for item in result.get("findings", []) or []:
        if not isinstance(item, dict):
            continue
        damage_type = str(item.get("damage_type", "unknown")).lower()
        if damage_type not in DAMAGE_TYPES:
            damage_type = "unknown"
        finding_severity = str(item.get("severity", "UNDETERMINED")).upper()
        if finding_severity not in SEVERITIES:
            finding_severity = "UNDETERMINED"
        findings.append({
            "damage_type": damage_type,
            "severity": finding_severity,
            "confidence": item.get("confidence"),
            "observation": str(item.get("observation", "")).strip(),
            "location": str(item.get("location", "")).strip(),
        })
    return {
        "image_quality": quality,
        "overall_severity": severity,
        "confidence": confidence,
        "findings": findings,
        "summary": str(result.get("summary", "")).strip(),
        "retake_requested": bool(result.get("retake_requested", quality in {"POOR", "INSUFFICIENT"})),
    }


def inspect_image(image_bytes: bytes, filename: str, line_id: str, model: str = MODEL_DEFAULT) -> dict[str, Any]:
    """Send one inspection photo to the vision model and return normalized findings."""
    if not ai_is_configured():
        raise RuntimeError("OPENAI_API_KEY is not configured in Streamlit Secrets.")
    if not image_bytes:
        raise ValueError("Inspection image is empty.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise ValueError("Inspection image is larger than 12 MB.")

    from openai import OpenAI

    mime = mimetypes.guess_type(filename)[0] or "image/jpeg"
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        raise ValueError("Unsupported image type. Use JPEG, PNG, WEBP, or GIF.")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"

    instruction = f"""You are an AI visual inspection assistant for a ship's mooring-line maintenance record.
Line ID: {line_id}.

Analyze ONLY what is visibly supported by the photograph. Identify visible damage
such as abrasion, glazing/heat damage, broken yarns/strands, cuts, chemical or
contamination effects, deformation/flattening, sheath/cover damage, splice/end
damage, or unknown.

Rules:
- Do not estimate a wear percentage.
- Do not estimate residual breaking strength, MBL, LDBF, WLL, or remaining life.
- Do not declare the line safe/unsafe for operation and do not recommend replacement.
- Severity is visual severity of the observed condition only.
- If the image is blurred, too distant, badly exposed, obstructed, or otherwise
  insufficient for a reliable visual assessment, set retake_requested=true and
  explain what additional photo would be useful.
- Return JSON only.

Required JSON shape:
{{
  "image_quality": "GOOD|ACCEPTABLE|POOR|INSUFFICIENT|UNDETERMINED",
  "overall_severity": "NONE|LOW|MODERATE|HIGH|CRITICAL|UNDETERMINED",
  "confidence": 0.0,
  "findings": [
    {{"damage_type":"abrasion|glazing_or_heat_damage|broken_yarns_or_strands|cut_or_severed_fibres|chemical_or_contamination|deformation_or_flattening|sheath_or_cover_damage|splice_or_end_damage|unknown", "severity":"NONE|LOW|MODERATE|HIGH|CRITICAL|UNDETERMINED", "confidence":0.0, "observation":"", "location":""}}
  ],
  "summary": "",
  "retake_requested": false
}}"""

    client = OpenAI(api_key=_secret("OPENAI_API_KEY"))
    response = client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": instruction},
                {"type": "input_image", "image_url": data_url, "detail": "high"},
            ],
        }],
    )
    result = _normalize(_parse_json(response.output_text))
    result["inspection_id"] = str(uuid.uuid4())
    result["line_id"] = str(line_id)
    result["timestamp_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["model"] = model
    result["image_sha256"] = __import__("hashlib").sha256(image_bytes).hexdigest()
    result["image_mime"] = mime
    result["image_filename"] = filename
    return result


def save_inspection(result: dict[str, Any], image_bytes: bytes) -> None:
    init_ai_repository()
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.execute(
        """INSERT INTO ai_line_inspections
        (inspection_id,line_id,timestamp_utc,model,image_sha256,image_mime,image_blob,
         image_quality,overall_severity,confidence,findings_json,ai_summary,retake_requested,
         operator_status,operator_note,confirmed_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            result["inspection_id"], result["line_id"], result["timestamp_utc"], result["model"],
            result["image_sha256"], result["image_mime"], sqlite3.Binary(image_bytes),
            result["image_quality"], result["overall_severity"], result.get("confidence"),
            json.dumps(result.get("findings", []), ensure_ascii=False), result.get("summary", ""),
            1 if result.get("retake_requested") else 0, "PENDING_OPERATOR_CONFIRMATION", "", None,
        ),
    )
    conn.commit()
    conn.close()


def list_inspections(line_id: str | None = None) -> list[dict[str, Any]]:
    init_ai_repository()
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    if line_id:
        rows = conn.execute(
            "SELECT inspection_id,line_id,timestamp_utc,model,image_sha256,image_quality,overall_severity,confidence,findings_json,ai_summary,retake_requested,operator_status,operator_note,confirmed_at_utc FROM ai_line_inspections WHERE line_id=? ORDER BY timestamp_utc DESC",
            (str(line_id),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT inspection_id,line_id,timestamp_utc,model,image_sha256,image_quality,overall_severity,confidence,findings_json,ai_summary,retake_requested,operator_status,operator_note,confirmed_at_utc FROM ai_line_inspections ORDER BY timestamp_utc DESC"
        ).fetchall()
    conn.close()
    columns = ["inspection_id","line_id","timestamp_utc","model","image_sha256","image_quality","overall_severity","confidence","findings_json","ai_summary","retake_requested","operator_status","operator_note","confirmed_at_utc"]
    return [dict(zip(columns, row)) for row in rows]


def get_inspection_image(inspection_id: str) -> bytes | None:
    init_ai_repository()
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    row = conn.execute("SELECT image_blob FROM ai_line_inspections WHERE inspection_id=?", (inspection_id,)).fetchone()
    conn.close()
    return bytes(row[0]) if row and row[0] is not None else None


def confirm_inspection(inspection_id: str, operator_note: str = "") -> None:
    init_ai_repository()
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.execute(
        "UPDATE ai_line_inspections SET operator_status='OPERATOR_CONFIRMED', operator_note=?, confirmed_at_utc=? WHERE inspection_id=?",
        (str(operator_note).strip(), datetime.now(timezone.utc).isoformat(timespec="seconds"), inspection_id),
    )
    conn.commit()
    conn.close()
