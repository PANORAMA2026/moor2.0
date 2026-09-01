"""Auditable lifecycle model for recording a mooring operation."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class SessionStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class LineExposure:
    line_id: str
    timestamp_utc: str
    tension_n: float | None
    mbl_n: float | None
    utilization_pct: float | None
    duration_s: float
    source: str = "SOLVER"
    valid: bool = True
    diagnostic: str = ""


@dataclass(frozen=True)
class EnvironmentalObservation:
    timestamp_utc: str
    wind_speed_mps: float | None
    wind_direction_deg: float | None
    gust_mps: float | None
    current_speed_mps: float | None
    current_direction_deg: float | None
    wave_height_m: float | None
    wave_period_s: float | None
    provider: str
    source_kind: str
    forecast_reference_time: str | None = None
    tidal_current_u_mps: float | None = None
    tidal_current_v_mps: float | None = None
    water_level_m: float | None = None
    water_level_datum: str | None = None


@dataclass
class MooringSession:
    session_id: str
    port_name: str
    berth_name: str | None
    start_utc: str | None = None
    scheduled_start_utc: str | None = None
    scheduled_end_utc: str | None = None
    end_utc: str | None = None
    status: SessionStatus = SessionStatus.SCHEDULED
    schedule_id: str | None = None
    setup_name: str | None = None
    setup_source: str = "SCHEDULE"
    schedule_fingerprint: str | None = None
    environmental_observations: list[EnvironmentalObservation] = field(default_factory=list)
    line_exposures: list[LineExposure] = field(default_factory=list)
    notes: str = ""

    def start(self, start_utc: str | None = None) -> None:
        if self.status is not SessionStatus.SCHEDULED:
            raise ValueError("Only a scheduled session can be started")
        self.start_utc = start_utc or datetime.now(timezone.utc).isoformat()
        self.status = SessionStatus.ACTIVE

    def stop(self, end_utc: str | None = None) -> None:
        if self.status is not SessionStatus.ACTIVE:
            raise ValueError("Only an active session can be stopped")
        self.end_utc = end_utc or datetime.now(timezone.utc).isoformat()
        self.status = SessionStatus.COMPLETED

    def cancel(self) -> None:
        if self.status not in (SessionStatus.SCHEDULED, SessionStatus.ACTIVE):
            raise ValueError("Only a scheduled or active session can be cancelled")
        self.status = SessionStatus.CANCELLED
        self.end_utc = datetime.now(timezone.utc).isoformat()

    def add_environment(self, observation: EnvironmentalObservation) -> None:
        if self.status is not SessionStatus.ACTIVE:
            raise ValueError("Cannot add observations to a closed or scheduled session")
        self.environmental_observations.append(observation)

    def add_exposure(self, exposure: LineExposure) -> None:
        if self.status is not SessionStatus.ACTIVE:
            raise ValueError("Cannot add line exposure to a closed or scheduled session")
        if exposure.duration_s < 0:
            raise ValueError("Exposure duration cannot be negative")
        if exposure.mbl_n is not None and exposure.mbl_n <= 0:
            raise ValueError("MBL must be greater than zero when supplied")
        if exposure.tension_n is not None and exposure.tension_n < 0:
            raise ValueError("Tension cannot be negative")
        self.line_exposures.append(exposure)

    def total_line_hours(self, line_id: str) -> float:
        return sum(e.duration_s for e in self.line_exposures if e.line_id == line_id and e.valid) / 3600.0


def new_session(
    session_id: str,
    port_name: str,
    berth_name: str | None = None,
    scheduled_start_utc: str | None = None,
    scheduled_end_utc: str | None = None,
    schedule_id: str | None = None,
    setup_name: str | None = None,
    setup_source: str = "SCHEDULE",
    schedule_fingerprint: str | None = None,
) -> MooringSession:
    return MooringSession(
        session_id=session_id,
        port_name=port_name,
        berth_name=berth_name,
        scheduled_start_utc=scheduled_start_utc,
        scheduled_end_utc=scheduled_end_utc,
        schedule_id=schedule_id,
        setup_name=setup_name,
        setup_source=setup_source,
        schedule_fingerprint=schedule_fingerprint,
    )
