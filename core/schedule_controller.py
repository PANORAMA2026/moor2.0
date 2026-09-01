"""Deterministic controller that converts the port-call calendar into sessions.

Normal operation is intentionally automatic. The controller selects the active
port call, resolves the configured/default mooring setup, and creates a stable
session identity. A schedule fingerprint detects changes so an operator is only
asked to intervene when the schedule or setup actually changes.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from core.mooring_session import MooringSession, SessionStatus, new_session


@dataclass(frozen=True)
class ScheduleDecision:
    action: str
    reason: str
    session: MooringSession | None = None
    requires_operator: bool = False


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def schedule_fingerprint(port: str, eta: Any, etd: Any, berth: str | None, setup: str | None) -> str:
    raw = "|".join((_norm(port), _norm(eta), _norm(etd), _norm(berth), _norm(setup)))
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def session_id_for_schedule(port: str, eta: Any, etd: Any) -> str:
    raw = "|".join((_norm(port), _norm(eta), _norm(etd)))
    return "MOOR-" + sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return default


def decide_for_active_call(row: Any, setup_name: str | None = None) -> ScheduleDecision:
    """Build a deterministic scheduled session from one calendar row.

    This function never silently overwrites an existing active session. The
    caller should compare the returned fingerprint with the persisted session.
    """
    port = _norm(_row_value(row, "Port"))
    eta = _row_value(row, "ETA")
    etd = _row_value(row, "ETD")
    berth = _row_value(row, "Berth", _row_value(row, "Berth_Type"))

    if not port or eta is None or etd is None:
        return ScheduleDecision("NO_ACTION", "Incomplete port-call row")

    fingerprint = schedule_fingerprint(port, eta, etd, berth, setup_name)
    session = new_session(
        session_id=session_id_for_schedule(port, eta, etd),
        port_name=port,
        berth_name=_norm(berth) or None,
        scheduled_start_utc=_norm(eta),
        scheduled_end_utc=_norm(etd),
        schedule_id=session_id_for_schedule(port, eta, etd),
        setup_name=setup_name,
        setup_source="SCHEDULE" if setup_name else "DEFAULT_SETUP",
        schedule_fingerprint=fingerprint,
    )
    return ScheduleDecision("UPSERT_SCHEDULED", "Active calendar call resolved", session)


def reconcile(existing: MooringSession | None, proposed: MooringSession) -> ScheduleDecision:
    """Reconcile calendar state without disrupting an active operation."""
    if existing is None:
        return ScheduleDecision("CREATE", "No existing session", proposed)

    if existing.status is SessionStatus.ACTIVE:
        if existing.schedule_fingerprint != proposed.schedule_fingerprint:
            return ScheduleDecision(
                "FLAG_SCHEDULE_CHANGE",
                "Calendar/setup changed while session is active; preserve active record and require operator review",
                existing,
                True,
            )
        return ScheduleDecision("KEEP_ACTIVE", "Active session matches calendar", existing)

    if existing.status is SessionStatus.COMPLETED:
        if existing.schedule_fingerprint == proposed.schedule_fingerprint:
            return ScheduleDecision("KEEP_COMPLETED", "Completed session matches calendar", existing)
        return ScheduleDecision("CREATE_NEW", "Calendar call changed after completion", proposed, True)

    if existing.schedule_fingerprint == proposed.schedule_fingerprint:
        return ScheduleDecision("KEEP_SCHEDULED", "Scheduled session matches calendar", existing)

    return ScheduleDecision(
        "UPDATE_SCHEDULED",
        "Calendar or mooring setup changed before operation started",
        proposed,
        True,
    )
