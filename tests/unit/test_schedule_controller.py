from core.mooring_session import SessionStatus
from core.schedule_controller import decide_for_active_call, reconcile


def test_schedule_row_creates_deterministic_scheduled_session():
    row = {"Port": "Long Beach Cruise Terminal", "ETA": "2026-09-01T10:00:00Z", "ETD": "2026-09-01T18:00:00Z", "Berth": "A"}
    decision = decide_for_active_call(row, setup_name="Default Standard")
    assert decision.action == "UPSERT_SCHEDULED"
    assert decision.session is not None
    assert decision.session.status is SessionStatus.SCHEDULED
    assert decision.session.setup_name == "Default Standard"
    assert decision.session.schedule_fingerprint


def test_active_session_is_never_silently_replaced_on_schedule_change():
    row = {"Port": "Long Beach Cruise Terminal", "ETA": "2026-09-01T10:00:00Z", "ETD": "2026-09-01T18:00:00Z", "Berth": "A"}
    proposed = decide_for_active_call(row, setup_name="Default Standard").session
    proposed.start("2026-09-01T11:00:00Z")
    changed = decide_for_active_call({**row, "ETD": "2026-09-01T19:00:00Z"}, setup_name="Default Standard").session

    decision = reconcile(proposed, changed)
    assert decision.action == "FLAG_SCHEDULE_CHANGE"
    assert decision.requires_operator is True
    assert decision.session is proposed
    assert proposed.status is SessionStatus.ACTIVE


def test_matching_active_session_remains_active_without_operator():
    row = {"Port": "Long Beach Cruise Terminal", "ETA": "2026-09-01T10:00:00Z", "ETD": "2026-09-01T18:00:00Z", "Berth": "A"}
    first = decide_for_active_call(row, setup_name="Default Standard").session
    first.start("2026-09-01T11:00:00Z")
    second = decide_for_active_call(row, setup_name="Default Standard").session

    decision = reconcile(first, second)
    assert decision.action == "KEEP_ACTIVE"
    assert decision.requires_operator is False
