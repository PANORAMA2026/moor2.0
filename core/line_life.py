"""Auditable line-history analytics.

This module records and summarizes exposure evidence. It deliberately does NOT
infer retirement, replacement, or end-for-ending requirements without an
explicit validated rule supplied by the operator, manufacturer, or governing
standard.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from core.mooring_session import LineExposure


class LifecycleEventType(str, Enum):
    INSTALLED = "INSTALLED"
    INSPECTION = "INSPECTION"
    MAINTENANCE = "MAINTENANCE"
    END_FOR_END = "END_FOR_END"
    REPLACED = "REPLACED"
    REMOVED = "REMOVED"
    OTHER = "OTHER"


@dataclass(frozen=True)
class LineLifecycleEvent:
    line_id: str
    event_type: LifecycleEventType
    timestamp_utc: str
    notes: str = ""
    source: str = "MANUAL"


@dataclass(frozen=True)
class LoadBandExposure:
    lower_pct: float
    upper_pct: float | None
    duration_s: float


@dataclass(frozen=True)
class LineLifeSummary:
    line_id: str
    exposure_hours: float
    sample_count: int
    max_utilization_pct: float | None
    mean_utilization_pct: float | None
    utilization_hours_over_wll: float | None
    high_load_event_count: int
    load_bands: tuple[LoadBandExposure, ...]
    status: str
    reason: str


# Bands are relative to Ship Design MBL. They are history buckets, not
# retirement criteria and do not replace line-specific WLL or manufacturer data.
_DEFAULT_BANDS = (
    (0.0, 10.0),
    (10.0, 20.0),
    (20.0, 30.0),
    (30.0, 40.0),
    (40.0, 50.0),
    (50.0, None),
)


def summarize_exposure(
    exposures: Iterable[LineExposure],
    line_id: str,
    *,
    wll_pct: float | None = None,
    high_load_pct: float = 50.0,
) -> LineLifeSummary:
    """Summarize valid exposure records for one line.

    ``wll_pct`` must come from the applicable certified/validated rule for the
    actual line. No default WLL is silently assumed here.
    """
    rows = [e for e in exposures if e.line_id == line_id and e.valid and e.duration_s >= 0]
    rows_with_util = [e for e in rows if e.utilization_pct is not None]

    total_s = sum(e.duration_s for e in rows)
    utilizations = [float(e.utilization_pct) for e in rows_with_util]

    over_wll_s = None
    if wll_pct is not None:
        over_wll_s = sum(e.duration_s for e in rows_with_util if e.utilization_pct > wll_pct)

    high_load_events = 0
    was_high = False
    for e in rows:
        is_high = e.utilization_pct is not None and e.utilization_pct >= high_load_pct
        if is_high and not was_high:
            high_load_events += 1
        was_high = is_high

    bands = tuple(
        LoadBandExposure(
            lower_pct=lower,
            upper_pct=upper,
            duration_s=sum(
                e.duration_s
                for e in rows_with_util
                if e.utilization_pct >= lower
                and (upper is None or e.utilization_pct < upper)
            ),
        )
        for lower, upper in _DEFAULT_BANDS
    )

    if not rows:
        status = "NO_DATA"
        reason = "No valid session exposure data."
    else:
        status = "DATA_ONLY"
        reason = (
            "Exposure metrics only; no replacement or end-for-ending decision "
            "is inferred without validated service-life criteria."
        )

    return LineLifeSummary(
        line_id=line_id,
        exposure_hours=total_s / 3600.0,
        sample_count=len(rows),
        max_utilization_pct=max(utilizations) if utilizations else None,
        mean_utilization_pct=(
            sum(e.utilization_pct * e.duration_s for e in rows_with_util) / total_s
            if total_s > 0 and rows_with_util else None
        ),
        utilization_hours_over_wll=(over_wll_s / 3600.0 if over_wll_s is not None else None),
        high_load_event_count=high_load_events,
        load_bands=bands,
        status=status,
        reason=reason,
    )


def summarize_all(exposures: Iterable[LineExposure]) -> dict[str, LineLifeSummary]:
    """Return one summary for every line represented in the exposure records."""
    rows = list(exposures)
    line_ids = {e.line_id for e in rows}
    return {line_id: summarize_exposure(rows, line_id) for line_id in sorted(line_ids)}


@dataclass
class LineHistory:
    """Lifecycle evidence for one physical line or tail."""

    line_id: str
    installation_date_utc: str | None = None
    events: list[LineLifecycleEvent] = field(default_factory=list)

    def add_event(self, event: LineLifecycleEvent) -> None:
        if event.line_id != self.line_id:
            raise ValueError("Lifecycle event line_id does not match history line_id")
        self.events.append(event)

    def end_for_end_count(self) -> int:
        return sum(e.event_type is LifecycleEventType.END_FOR_END for e in self.events)

    def replacement_count(self) -> int:
        return sum(e.event_type is LifecycleEventType.REPLACED for e in self.events)

    def latest_event(self) -> LineLifecycleEvent | None:
        return max(self.events, key=lambda e: e.timestamp_utc) if self.events else None

    def assessment_status(self) -> str:
        """Conservative state: lifecycle data exists, but life is not assessed."""
        if not self.installation_date_utc and not self.events:
            return "NOT_ASSESSED"
        return "DATA_ONLY"
