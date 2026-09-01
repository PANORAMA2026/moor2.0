"""Automatic reconciliation of the port-call calendar with mooring sessions."""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
from core.schedule_controller import decide_for_active_call, reconcile
from database.db_manager import get_port_mooring_setups
from database.mooring_session_repository import save_session, load_by_session_id, load_active_or_scheduled


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value) -> datetime | None:
    if value is None or pd.isna(value): return None
    dt = pd.to_datetime(value).to_pydatetime()
    if dt.tzinfo is None: return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _active_row(schedule: pd.DataFrame, now: datetime):
    if schedule is None or schedule.empty: return None
    rows = schedule.copy()
    rows["ETA"] = pd.to_datetime(rows["ETA"], errors="coerce")
    rows["ETD"] = pd.to_datetime(rows["ETD"], errors="coerce")
    rows = rows.dropna(subset=["ETA", "ETD"])
    for _, row in rows.sort_values("ETA").iterrows():
        eta, etd = _as_utc(row["ETA"]), _as_utc(row["ETD"])
        if eta and etd and eta <= now <= etd: return row
    return None


def resolve_setup(port: str) -> tuple[str | None, str]:
    setups = get_port_mooring_setups(port)
    if not setups: return None, "NO_SETUP"
    if "Default Standard" in setups: return "Default Standard", "PORT_DEFAULT"
    return next(iter(setups)), "PORT_SETUP"


def reconcile_schedule(schedule: pd.DataFrame, now: datetime | None = None) -> dict:
    now = now or _utc_now()
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
        if _as_utc(current.scheduled_start_utc) and now >= _as_utc(current.scheduled_start_utc):
            current.start(_as_utc(current.scheduled_start_utc).isoformat()); save_session(current)
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
