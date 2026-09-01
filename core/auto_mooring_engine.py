"""Automatic mooring exposure logger.

This service records operational exposure only when the source data are
explicitly supplied. It deliberately does not invent weather or line tension.
The Streamlit UI is a caller, not a background scheduler; a real scheduler or
external telemetry source must invoke this service periodically.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class WeatherReading:
    wind_speed_kts: float
    wind_dir_deg: float
    source: str
    timestamp: datetime

    def validate(self) -> None:
        if self.wind_speed_kts < 0:
            raise ValueError("Wind speed cannot be negative.")
        if not 0.0 <= self.wind_dir_deg < 360.0:
            raise ValueError("Wind direction must be in [0, 360) degrees.")
        if not self.source.strip():
            raise ValueError("Weather source is required.")


def fetch_live_weather(port_name: str) -> Optional[WeatherReading]:
    """Return no data until a real weather provider is configured.

    The previous implementation returned hard-coded 'live' weather. That is
    unsafe for engineering logging because it could create false exposure
    records. A provider will be injected here in a later integration stage.
    """
    _ = port_name
    return None


def _get_active_port(schedule: pd.DataFrame, now: datetime) -> Optional[pd.Series]:
    required = {"ETA", "ETD", "Port"}
    missing = required - set(schedule.columns)
    if missing:
        raise ValueError(f"Schedule missing required columns: {', '.join(sorted(missing))}")
    active = schedule[(schedule["ETA"] <= now) & (schedule["ETD"] >= now)]
    return None if active.empty else active.iloc[0]


def process_automatic_mooring_logging(
    *,
    now: Optional[datetime] = None,
    weather: Optional[WeatherReading] = None,
    line_exposure: Optional[pd.DataFrame] = None,
) -> dict:
    """Process one automatic-monitoring cycle without fabricating engineering data.

    ``line_exposure`` is expected to contain already-calculated engineering
    results, including line_id, tension/utilisation and the source/calculation
    status. This service does not derive tension from wind with an arbitrary
    multiplier.
    """
    if "port_schedule" not in st.session_state or st.session_state["port_schedule"].empty:
        return {"status": "NO_SCHEDULE", "message": "Nessun calendario caricato."}

    now = now or datetime.now()
    schedule = st.session_state["port_schedule"]
    row = _get_active_port(schedule, now)

    if row is None:
        st.session_state.pop("active_mooring_session", None)
        return {"status": "IN_TRANSIT", "message": "Nave in navigazione. Nessun ormeggio attivo."}

    port_name = str(row["Port"])
    eta = row["ETA"]
    etd = row["ETD"]
    session_key = f"session_{port_name}_{eta.strftime('%Y%m%d_%H%M')}"

    session = st.session_state.get("active_mooring_session")
    if session is None or session.get("id") != session_key:
        session = {
            "id": session_key,
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "last_sync_time": now,
            "last_logged_wind": None,
            "accumulated_interval_hours": 0.0,
        }
        st.session_state["active_mooring_session"] = session

    weather_override_key = f"weather_override_{port_name}"
    if weather_override_key in st.session_state:
        weather = WeatherReading(
            wind_speed_kts=float(st.session_state[weather_override_key]["wind_speed"]),
            wind_dir_deg=float(st.session_state[weather_override_key].get("wind_dir_deg", 0.0)),
            source="MANUAL_OPERATOR_OVERRIDE",
            timestamp=now,
        )

    if weather is None:
        weather = fetch_live_weather(port_name)

    if weather is None:
        return {
            "status": "DATA_UNAVAILABLE",
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "hours_in_port": max(0.0, (now - eta).total_seconds() / 3600.0),
            "current_wind": None,
            "weather_src": "UNAVAILABLE",
            "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
            "last_trigger": "No weather source configured",
            "summary": pd.DataFrame(),
            "warning": "No automatic engineering logging performed: weather source unavailable.",
        }

    weather.validate()
    last_wind = session["last_logged_wind"]
    elapsed_hours = max(0.0, (now - session["last_sync_time"]).total_seconds() / 3600.0)
    wind_event = last_wind is not None and abs(weather.wind_speed_kts - last_wind) >= 6.0
    interval_event = elapsed_hours >= 0.5

    trigger = "Wind Delta >= 6 kt" if wind_event else ("Interval >= 30 min" if interval_event else None)
    summary = pd.DataFrame()

    if trigger and line_exposure is not None and not line_exposure.empty:
        required = {"line_id", "tension_tons", "utilization_pct", "calculation_status"}
        missing = required - set(line_exposure.columns)
        if missing:
            raise ValueError(f"Line exposure missing required fields: {', '.join(sorted(missing))}")

        # Only persist an exposure record if the engineering calculation has
        # explicitly declared itself valid/converged.
        valid = line_exposure[line_exposure["calculation_status"].astype(str).str.upper() == "VALID"]
        if not valid.empty:
            summary = valid.copy()
            summary["last_port"] = port_name
            summary["interval_hours"] = elapsed_hours
            summary["trigger_event"] = trigger
            summary["weather_source"] = weather.source
            summary["last_auto_sync"] = now.strftime("%Y-%m-%d %H:%M:%S")

    if trigger:
        session["last_sync_time"] = now
        session["last_logged_wind"] = weather.wind_speed_kts
        session["accumulated_interval_hours"] += elapsed_hours

    return {
        "status": "IN_PORT",
        "port": port_name,
        "eta": eta,
        "etd": etd,
        "hours_in_port": max(0.0, (now - eta).total_seconds() / 3600.0),
        "current_wind": weather.wind_speed_kts,
        "weather_src": weather.source,
        "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
        "last_trigger": trigger or "Monitoring...",
        "summary": summary,
    }
