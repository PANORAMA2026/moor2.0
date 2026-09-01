"""Normalized environmental input contract for mooring sessions.

The purpose of this module is traceability: every engineering calculation can
consume one explicit environmental state with source/provenance information.
Forecast and observed data remain distinguishable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from core.tidal_models import TidalState


@dataclass(frozen=True)
class EnvironmentalState:
    timestamp_utc: datetime
    wind_speed_mps: float | None = None
    wind_direction_from_deg_true: float | None = None
    gust_speed_mps: float | None = None
    current_speed_mps: float | None = None
    current_direction_to_deg_true: float | None = None
    tidal_current_u_mps: float | None = None
    tidal_current_v_mps: float | None = None
    wave_height_m: float | None = None
    wave_period_s: float | None = None
    water_level_m: float | None = None
    water_level_datum: str | None = None
    provider: str = "UNSPECIFIED"
    source_kind: str = "UNKNOWN"
    forecast_reference_time: datetime | None = None

    def validate(self) -> None:
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("Environmental timestamp must be timezone-aware.")
        for value, label in (
            (self.wind_speed_mps, "Wind speed"),
            (self.gust_speed_mps, "Wind gust speed"),
            (self.current_speed_mps, "Current speed"),
            (self.wave_height_m, "Wave height"),
            (self.wave_period_s, "Wave period"),
        ):
            if value is not None and value < 0:
                raise ValueError(f"{label} cannot be negative.")
        for value, label in (
            (self.wind_direction_from_deg_true, "Wind direction"),
            (self.current_direction_to_deg_true, "Current direction"),
        ):
            if value is not None and not 0.0 <= value <= 360.0:
                raise ValueError(f"{label} must be between 0 and 360 degrees.")

    @classmethod
    def from_tidal_state(
        cls,
        timestamp_utc: datetime,
        *,
        wind_speed_mps: float | None = None,
        wind_direction_from_deg_true: float | None = None,
        gust_speed_mps: float | None = None,
        current_speed_mps: float | None = None,
        current_direction_to_deg_true: float | None = None,
        wave_height_m: float | None = None,
        wave_period_s: float | None = None,
        tidal_state: TidalState | None = None,
        provider: str = "UNSPECIFIED",
        source_kind: str = "UNKNOWN",
        forecast_reference_time: datetime | None = None,
    ) -> "EnvironmentalState":
        if timestamp_utc.tzinfo is None:
            timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
        if tidal_state is not None:
            if tidal_state.timestamp_utc.tzinfo is None:
                raise ValueError("Tidal timestamp must be timezone-aware.")
            water_level_m = tidal_state.water_level_m
            water_level_datum = tidal_state.datum
            tidal_u = tidal_state.tidal_current_u_mps
            tidal_v = tidal_state.tidal_current_v_mps
        else:
            water_level_m = None
            water_level_datum = None
            tidal_u = None
            tidal_v = None

        state = cls(
            timestamp_utc=timestamp_utc.astimezone(timezone.utc),
            wind_speed_mps=wind_speed_mps,
            wind_direction_from_deg_true=wind_direction_from_deg_true,
            gust_speed_mps=gust_speed_mps,
            current_speed_mps=current_speed_mps,
            current_direction_to_deg_true=current_direction_to_deg_true,
            tidal_current_u_mps=tidal_u,
            tidal_current_v_mps=tidal_v,
            wave_height_m=wave_height_m,
            wave_period_s=wave_period_s,
            water_level_m=water_level_m,
            water_level_datum=water_level_datum,
            provider=provider,
            source_kind=source_kind,
            forecast_reference_time=forecast_reference_time,
        )
        state.validate()
        return state
