from core.line_life import LifecycleEventType, LineHistory, LineLifecycleEvent, summarize_exposure
from core.mooring_session import LineExposure


def exposure(tension_pct: float, duration_s: float, valid: bool = True) -> LineExposure:
    return LineExposure(
        line_id="M1",
        timestamp_utc="2026-09-01T12:00:00+00:00",
        tension_n=1000.0,
        mbl_n=10000.0,
        utilization_pct=tension_pct,
        duration_s=duration_s,
        valid=valid,
    )


def test_summary_uses_only_valid_exposure_and_keeps_wll_explicit():
    result = summarize_exposure(
        [exposure(20.0, 60), exposure(60.0, 120), exposure(80.0, 30, valid=False)],
        "M1",
        wll_pct=55.0,
    )
    assert result.sample_count == 2
    assert result.exposure_hours == 180 / 3600
    assert result.max_utilization_pct == 60.0
    assert result.utilization_hours_over_wll == 120 / 3600


def test_high_load_events_count_contiguous_periods():
    result = summarize_exposure(
        [exposure(55.0, 60), exposure(60.0, 60), exposure(20.0, 60), exposure(70.0, 60)],
        "M1",
    )
    assert result.high_load_event_count == 2


def test_no_data_is_not_a_replacement_decision():
    result = summarize_exposure([], "M1")
    assert result.status == "NO_DATA"
    assert "replacement" in result.reason


def test_line_history_records_end_for_end_and_replacement_events():
    history = LineHistory(line_id="M1", installation_date_utc="2026-01-01T00:00:00+00:00")
    history.add_event(LineLifecycleEvent("M1", LifecycleEventType.INSPECTION, "2026-06-01T00:00:00+00:00"))
    history.add_event(LineLifecycleEvent("M1", LifecycleEventType.END_FOR_END, "2026-07-01T00:00:00+00:00"))
    history.add_event(LineLifecycleEvent("M1", LifecycleEventType.REPLACED, "2026-08-01T00:00:00+00:00"))
    assert history.end_for_end_count() == 1
    assert history.replacement_count() == 1
    assert history.assessment_status() == "DATA_ONLY"
