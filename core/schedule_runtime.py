"""Automatic reconciliation of the port-call calendar with mooring sessions."""
from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from zoneinfo import ZoneInfo

import pandas as pd

from config.constants import DB_FILE_PATH, PORT_COORDINATES
from core.schedule_controller import decide_for_active_call, reconcile
from database.db_manager import get_port_mooring_setups
from database.mooring_session_repository import (
    save_session,
    load_by_session_id,
    load_active_or_scheduled,
)


PORT_TIMEZONES = {
    "LGB": "America/Los_Angeles",
    "ENS": "America/Tijuana",
    "CSL": "America/Mazatlan",
    "MZT": "America/Mazatlan",
    "PVR": "America/Bahia_Banderas",
}

# Calendar names and engineering/configuration names are not always identical.
# The port code remains the preferred bridge between the two systems.
PORT_ALIASES = {
    "LGB": ["Long Beach Cruise Terminal"],
    "ENS": ["Ensenada Pier #2"],
    "CSL": ["Cabo San Lucas"],
    "MZT": ["Mazatlan Pier 4/5", "Mazatlan Pier 2/3"],
    "PVR": ["Puerto Vallarta Pier #1", "Puerto Vallarta Pier #3"],
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _port_timezone(row) -> ZoneInfo | None:
    try:
        code = str(row.get("Port_Code", "")).strip().upper()
    except AttributeError:
        code = ""
    tz_name = PORT_TIMEZONES.get(code)
    return ZoneInfo(tz_name) if tz_name else None


def _as_utc(value, row=None) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    dt = pd.to_datetime(value).to_pydatetime()
    if dt.tzinfo is None:
        tz = _port_timezone(row) if row is not None else None
        return dt.replace(tzinfo=tz or timezone.utc).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _local_naive(value) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    dt = pd.to_datetime(value).to_pydatetime()
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _active_row(schedule: pd.DataFrame, now: datetime):
    if schedule is None or schedule.empty:
        return None

    rows = schedule.copy()
    rows["ETA"] = pd.to_datetime(rows["ETA"], errors="coerce")
    rows["ETD"] = pd.to_datetime(rows["ETD"], errors="coerce")
    rows = rows.dropna(subset=["ETA", "ETD"])
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    candidates = []

    for _, row in rows.iterrows():
        tz = _port_timezone(row)
        eta_local = _local_naive(row["ETA"])
        etd_local = _local_naive(row["ETD"])
        if eta_local is None or etd_local is None:
            continue

        if tz is not None:
            local_now = now_utc.astimezone(tz).replace(tzinfo=None)
            if eta_local <= local_now <= etd_local:
                eta_utc = eta_local.replace(tzinfo=tz).astimezone(timezone.utc)
                etd_utc = etd_local.replace(tzinfo=tz).astimezone(timezone.utc)
                normalized = row.copy()
                normalized["ETA"] = eta_utc
                normalized["ETD"] = etd_utc
                candidates.append((eta_utc, normalized))
        else:
            eta_utc = _as_utc(row["ETA"], row)
            etd_utc = _as_utc(row["ETD"], row)
            if eta_utc and etd_utc and eta_utc <= now_utc <= etd_utc:
                normalized = row.copy()
                normalized["ETA"] = eta_utc
                normalized["ETD"] = etd_utc
                candidates.append((eta_utc, normalized))

    return sorted(candidates, key=lambda item: item[0])[-1][1] if candidates else None


def _configured_port_names() -> list[str]:
    """Return only ports explicitly represented by the engineering configuration."""
    return [str(name).strip() for name in PORT_COORDINATES if str(name).strip()]


def _normalize_name(value: str) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _resolve_configured_port(calendar_port: str, port_code: str | None) -> str | None:
    """Map an itinerary port to a real configured engineering port without fabricating one."""
    calendar_port = str(calendar_port or "").strip()
    code = str(port_code or "").strip().upper()
    configured = _configured_port_names()

    normalized = _normalize_name(calendar_port)
    for name in configured:
        if _normalize_name(name) == normalized:
            return name

    for alias in PORT_ALIASES.get(code, []):
        for name in configured:
            if _normalize_name(name) == _normalize_name(alias):
                return name

    return None


def _has_explicit_setup(port: str) -> bool:
    """Check the DB directly because get_port_mooring_setups() supplies a synthetic fallback."""
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    try:
        row = conn.execute(
            "SELECT 1 FROM port_mooring_setups WHERE port_name = ? LIMIT 1",
            (port,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def resolve_setup(port: str) -> tuple[str | None, str]:
    """Resolve an explicitly configured setup; never treat a synthetic fallback as configuration."""
    if not _has_explicit_setup(port):
        return None, "NO_SETUP"

    setups = get_port_mooring_setups(port)
    if not setups:
        return None, "NO_SETUP"
    if "Default Standard" in setups:
        return "Default Standard", "PORT_DEFAULT"
    return next(iter(setups)), "PORT_SETUP"


def reconcile_schedule(schedule: pd.DataFrame, now: datetime | None = None) -> dict:
    """Reconcile the calendar without confusing 'no setup' with 'at sea'."""
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    row = _active_row(schedule, now)
    existing = load_active_or_scheduled()

    for session in existing:
        end = _as_utc(session.scheduled_end_utc)
        if session.status.value == "ACTIVE" and end and now > end:
            session.stop(end.isoformat())
            save_session(session)

    # No calendar call covers the current instant: genuinely at sea.
    if row is None:
        return {
            "status": "IN_TRANSIT",
            "action": "NO_ACTIVE_PORT_CALL",
            "session": None,
            "operator": False,
            "port": None,
            "configured_port": None,
            "setup": None,
            "setup_source": "NO_PORT_CALL",
        }

    calendar_port = str(row["Port"]).strip()
    port_code = str(row.get("Port_Code", "")).strip().upper()
    configured_port = _resolve_configured_port(calendar_port, port_code)

    # The itinerary proves the vessel is in a port call. If the engineering
    # model has no matching configured port, expose a configuration exception.
    if not configured_port:
        return {
            "status": "PORT_CALL_ACTIVE_SETUP_MISSING",
            "action": "MOORING_PORT_NOT_CONFIGURED",
            "session": None,
            "operator": True,
            "port": calendar_port,
            "configured_port": None,
            "setup": None,
            "setup_source": "PORT_NOT_CONFIGURED",
            "scheduled_start_utc": _as_utc(row["ETA"], row).isoformat(),
            "scheduled_end_utc": _as_utc(row["ETD"], row).isoformat(),
        }

    setup_name, setup_source = resolve_setup(configured_port)

    # A valid port call is already established by the calendar. Missing setup
    # is a configuration/input problem, never evidence that the vessel is at sea.
    if not setup_name:
        return {
            "status": "PORT_CALL_ACTIVE_SETUP_MISSING",
            "action": "MOORING_SETUP_MISSING",
            "session": None,
            "operator": True,
            "port": calendar_port,
            "configured_port": configured_port,
            "setup": None,
            "setup_source": "NO_SETUP",
            "scheduled_start_utc": _as_utc(row["ETA"], row).isoformat(),
            "scheduled_end_utc": _as_utc(row["ETD"], row).isoformat(),
        }

    normalized_row = row.copy()
    normalized_row["Port"] = configured_port
    proposed_decision = decide_for_active_call(normalized_row, setup_name)
    proposed = proposed_decision.session
    if proposed is None:
        return {
            "status": "PORT_CALL_ACTIVE",
            "action": proposed_decision.action,
            "session": None,
            "operator": proposed_decision.requires_operator,
            "port": calendar_port,
            "configured_port": configured_port,
            "setup": setup_name,
            "setup_source": setup_source,
        }

    current = load_by_session_id(proposed.session_id)
    decision = reconcile(current, proposed)
    if decision.action in {"CREATE", "UPSERT_SCHEDULED", "UPDATE_SCHEDULED"}:
        target = proposed
        eta = _as_utc(target.scheduled_start_utc)
        if eta and now >= eta:
            target.start(eta.isoformat())
        save_session(target)
    elif decision.action == "KEEP_SCHEDULED" and current:
        eta = _as_utc(current.scheduled_start_utc)
        if eta and now >= eta:
            current.start(eta.isoformat())
            save_session(current)
    elif decision.action == "KEEP_ACTIVE" and current:
        save_session(current)

    session = load_by_session_id(proposed.session_id)
    return {
        "status": "MOORED" if session and session.status.value == "ACTIVE" else "SCHEDULED",
        "action": decision.action,
        "session": session,
        "operator": decision.requires_operator,
        "port": calendar_port,
        "configured_port": configured_port,
        "setup": setup_name,
        "setup_source": setup_source,
    }
