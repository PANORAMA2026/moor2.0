"""Domain model for a complete mooring session."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass(frozen=True)
class LineExposure:
    line_id: str
    timestamp_utc: str
    tension_n: float
    mbl_n: float
    utilization_pct: float
    duration_s: float
    source: str = "SOLVER"

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

@dataclass
class MooringSession:
    session_id: str
    port_name: str
    berth_name: str | None
    start_utc: str
    end_utc: str | None = None
    status: str = "ACTIVE"
    environmental_observations: list[EnvironmentalObservation] = field(default_factory=list)
    line_exposures: list[LineExposure] = field(default_factory=list)
    notes: str = ""

    def stop(self, end_utc: str | None = None) -> None:
        if self.status != "ACTIVE":
            raise ValueError("Only an active session can be stopped")
        self.end_utc = end_utc or datetime.now(timezone.utc).isoformat()
        self.status = "COMPLETED"

    def add_environment(self, observation: EnvironmentalObservation) -> None:
        if self.status != "ACTIVE":
            raise ValueError("Cannot add observations to a completed session")
        self.environmental_observations.append(observation)

    def add_exposure(self, exposure: LineExposure) -> None:
        if self.status != "ACTIVE":
            raise ValueError("Cannot add line exposure to a completed session")
        if exposure.mbl_n <= 0 or exposure.tension_n < 0:
            raise ValueError("Invalid line exposure values")
        self.line_exposures.append(exposure)

    def total_line_hours(self, line_id: str) -> float:
        return sum(e.duration_s for e in self.line_exposures if e.line_id == line_id) / 3600.0

def new_session(session_id: str, port_name: str, berth_name: str | None = None) -> MooringSession:
    return MooringSession(session_id=session_id, port_name=port_name, berth_name=berth_name,
                          start_utc=datetime.now(timezone.utc).isoformat())
