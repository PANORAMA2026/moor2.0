"""Line-life analytics foundation.

Reports exposure metrics, not a certified replacement limit. Replacement or
end-to-end decisions require validated manufacturer, inspection and MEG4
methodology inputs.
"""
from __future__ import annotations
from dataclasses import dataclass
from core.mooring_session import LineExposure

@dataclass(frozen=True)
class LineLifeSummary:
    line_id: str
    exposure_hours: float
    max_utilization_pct: float
    mean_utilization_pct: float
    utilization_hours_over_55_pct: float
    status: str
    reason: str

def summarize_exposure(exposures: list[LineExposure], line_id: str) -> LineLifeSummary:
    rows = [e for e in exposures if e.line_id == line_id]
    if not rows:
        return LineLifeSummary(line_id, 0.0, 0.0, 0.0, 0.0, "NO_DATA", "No session exposure data")
    total_s = max(sum(e.duration_s for e in rows), 1.0)
    hours = total_s / 3600.0
    max_util = max(e.utilization_pct for e in rows)
    mean_util = sum(e.utilization_pct * e.duration_s for e in rows) / total_s
    over55 = sum(e.duration_s for e in rows if e.utilization_pct >= 55.0) / 3600.0
    return LineLifeSummary(
        line_id=line_id, exposure_hours=hours, max_utilization_pct=max_util,
        mean_utilization_pct=mean_util, utilization_hours_over_55_pct=over55,
        status="REVIEW_REQUIRED" if max_util >= 55.0 else "MONITOR",
        reason="Exposure metric only; no replacement decision is inferred without validated service-life criteria.")
