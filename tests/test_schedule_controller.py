from core.mooring_session import SessionStatus, new_session
from core.schedule_controller import decide_for_active_call, reconcile


def _proposed():
    return decide_for_active_call(
        {
            "Port": "Ensenada Pier #2",
            "ETA": "2026-09-03T15:00:00+00:00",
            "ETD": "2026-09-04T21:00:00+00:00",
            "Berth": "Docked",
        },
        "Normal",
    ).session


def test_scheduled_operator_override_survives_scheduler_reconciliation():
    proposed = _proposed()
    existing = new_session(
        session_id=proposed.session_id,
        port_name=proposed.port_name,
        berth_name=proposed.berth_name,
        scheduled_start_utc=proposed.scheduled_start_utc,
        scheduled_end_utc=proposed.scheduled_end_utc,
        schedule_id=proposed.schedule_id,
        setup_name="Heavy Weather Alternative",
        setup_source="OPERATOR_OVERRIDE",
        schedule_fingerprint=proposed.schedule_fingerprint,
    )
    decision = reconcile(existing, proposed)
    assert decision.action == "KEEP_SCHEDULED"
    assert decision.requires_operator is False
    assert decision.session is existing
    assert decision.session.setup_name == "Heavy Weather Alternative"
    assert decision.session.setup_source == "OPERATOR_OVERRIDE"
    assert decision.session.status is SessionStatus.SCHEDULED


def test_active_operator_override_survives_scheduler_reconciliation():
    proposed = _proposed()
    existing = new_session(
        session_id=proposed.session_id,
        port_name=proposed.port_name,
        berth_name=proposed.berth_name,
        scheduled_start_utc=proposed.scheduled_start_utc,
        scheduled_end_utc=proposed.scheduled_end_utc,
        schedule_id=proposed.schedule_id,
        setup_name="Heavy Weather Alternative",
        setup_source="OPERATOR_OVERRIDE",
        schedule_fingerprint=proposed.schedule_fingerprint,
    )
    existing.start("2026-09-03T15:00:00+00:00")
    decision = reconcile(existing, proposed)
    assert decision.action == "KEEP_ACTIVE"
    assert decision.requires_operator is False
    assert decision.session.setup_name == "Heavy Weather Alternative"
