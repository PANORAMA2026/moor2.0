"""Automatic reconciliation of the port-call calendar with mooring sessions."""
from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd
from core.schedule_controller import decide_for_active_call, reconcile
from database.db_manager import get_port_mooring_setups
from database.mooring_session_repository import save_session, load_by_session_id, load_active_or_scheduled

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


def resolve_setup(port: str) -> tuple[str | None, str]:
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

    # No calendar call covers the current instant: this is genuinely at sea
    # (or outside the loaded itinerary window).
    if row is None:
        return {
            "status": "IN_TRANSIT",
            "action": "NO_ACTIVE_PORT_CALL",
            "session": None,
            "operator": False,
            "port": None,
            "setup": None,
            "setup_source": "NO_PORT_CALL",
        }

    port = str(row["Port"]).strip()
    setup_name, setup_source = resolve_setup(port)

    # A valid port call is already established by the calendar. Missing setup
    # is a configuration/input problem, never evidence that the vessel is at sea.
    if not setup_name:
        return {
            "status": "PORT_CALL_ACTIVE_SETUP_MISSING",
            "action": "MOORING_SETUP_MISSING",
            "session": None,
            "operator": True,
            "port": port,
            "setup": None,
            "setup_source": "NO_SETUP",
            "scheduled_start_utc": _as_utc(row["ETA"], row).isoformat(),
            "scheduled_end_utc": _as_utc(row["ETD"], row).isoformat(),
        }

    proposed_decision = decide_for_active_call(row, setup_name)
    proposed = proposed_decision.session
    if proposed is None:
        return {
            "status": "PORT_CALL_ACTIVE",
            "action": proposed_decision.action,
            "session": None,
            "operator": proposed_decision.requires_operator,
            "port": port,
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
        "setup": setup_name,
        "setup_source": setup_source,
        "port": port,
    }
