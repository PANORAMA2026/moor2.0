"""Automatic reconciliation of the port-call calendar with mooring sessions.

All itinerary ETA/ETD values are treated as *local port time* unless the
calendar already contains timezone-aware timestamps.  The runtime compares
those values in UTC, so the result is independent of the Streamlit server
location/timezone.
"""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from core.schedule_controller import decide_for_active_call, reconcile
from database.db_manager import get_port_mooring_setups
from database.mooring_session_repository import save_session, load_by_session_id, load_active_or_scheduled

# Time zones used by the Carnival Panorama itinerary.  Port Code is preferred
# over the display name because names can vary between itinerary exports.
PORT_TIMEZONES = {
    "LGB": "America/Los_Angeles",
    "ENS": "America/Tijuana",
    "CSL": "America/Mazatlan",
    "MZT": "America/Mazatlan",
    "PVR": "America/Bahia_Banderas",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _port_timezone(row) -> ZoneInfo | None:
    code = str(row.get("Port_Code", "")).strip().upper()
    tz_name = PORT_TIMEZONES.get(code)
    if tz_name:
        return ZoneInfo(tz_name)
    return None


def _as_utc(value, row=None) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    dt = pd.to_datetime(value).to_pydatetime()
    if dt.tzinfo is None:
        tz = _port_timezone(row) if row is not None else None
        # Session records created by the controller are already normalized to
        # UTC.  For a legacy naive session value, UTC is the safest fallback.
        return dt.replace(tzinfo=tz or timezone.utc).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def _active_row(schedule: pd.DataFrame, now: datetime):
    if schedule is None or schedule.empty:
        return None
    rows = schedule.copy()
    rows["ETA"] = pd.to_datetime(rows["ETA"], errors="coerce")
    rows["ETD"] = pd.to_datetime(rows["ETD"], errors="coerce")
    rows = rows.dropna(subset=["ETA", "ETD"])

    candidates = []
    for _, row in rows.iterrows():
        eta = _as_utc(row["ETA"], row)
        etd = _as_utc(row["ETD"], row)
        if eta and etd:
            candidates.append((eta, etd, row))

    for eta, etd, row in sorted(candidates, key=lambda item: item[0]):
        if eta <= now <= etd:
            # Return UTC-normalized timestamps to the session controller.
            normalized = row.copy()
            normalized["ETA"] = eta
            normalized["ETD"] = etd
            return normalized
    return None


def resolve_setup(port: str) -> tuple[str | None, str]:
    setups = get_port_mooring_setups(port)
    if not setups:
        return None, "NO_SETUP"
    if "Default Standard" in setups:
        return "Default Standard", "PORT_DEFAULT"
    return next(iter(setups)), "PORT_SETUP"


def reconcile_schedule(schedule: pd.DataFrame, now: datetime | None = None) -> dict:
    now = now or _utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    row = _active_row(schedule, now)
    existing = load_active_or_scheduled()

    # Close sessions whose scheduled port call has ended.
    for session in existing:
        end = _as_utc(session.scheduled_end_utc)
        if session.status.value == "ACTIVE" and end and now > end:
            session.stop(end.isoformat())
            save_session(session)

    if row is None:
        return {"status": "IN_TRANSIT", "action": "NO_ACTIVE_PORT_CALL", "session": None, "operator": False}

    setup_name, setup_source = resolve_setup(str(row["Port"]))
    proposed_decision = decide_for_active_call(row, setup_name)
    proposed = proposed_decision.session
    if proposed is None:
        return {"status": "NO_ACTION", "action": proposed_decision.action, "session": None, "operator": proposed_decision.requires_operator}

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
        "setup": setup_name,
        "setup_source": setup_source,
        "port": str(row["Port"]),
    }
