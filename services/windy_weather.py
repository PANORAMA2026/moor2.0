"""Windy Point Forecast integration.

API keys are runtime secrets only. Weather snapshots are marked FORECAST;
Windy Point Forecast is not a historical observation service.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import requests

WINDY_POINT_FORECAST_URL = "https://api.windy.com/api/point-forecast/v2"

@dataclass(frozen=True)
class WeatherSnapshot:
    timestamp_utc: str
    latitude: float
    longitude: float
    provider: str
    model: str
    wind_u_mps: float | None = None
    wind_v_mps: float | None = None
    gust_mps: float | None = None
    current_u_mps: float | None = None
    current_v_mps: float | None = None
    wave_height_m: float | None = None
    wave_period_s: float | None = None
    wave_direction_deg: float | None = None
    source_kind: str = "FORECAST"

    @property
    def wind_speed_mps(self) -> float | None:
        if self.wind_u_mps is None or self.wind_v_mps is None:
            return None
        return (self.wind_u_mps ** 2 + self.wind_v_mps ** 2) ** 0.5

class WindyConfigurationError(RuntimeError):
    pass

class WindyAPIError(RuntimeError):
    pass

def get_windy_api_key() -> str:
    key = os.getenv("WINDY_POINT_FORECAST_API_KEY")
    if not key:
        raise WindyConfigurationError("WINDY_POINT_FORECAST_API_KEY is not configured")
    return key

def fetch_point_forecast(lat: float, lon: float, model: str = "gfs", timeout_s: int = 15) -> dict[str, Any]:
    payload = {
        "lat": float(lat), "lon": float(lon), "model": model,
        "parameters": ["wind", "windGust", "waves", "currents"],
        "levels": ["surface"], "key": get_windy_api_key(),
    }
    response = requests.post(WINDY_POINT_FORECAST_URL, json=payload, timeout=timeout_s)
    if response.status_code != 200:
        raise WindyAPIError(f"Windy Point Forecast HTTP {response.status_code}: {response.text[:300]}")
    return response.json()

def snapshot_from_forecast(data: dict[str, Any], lat: float, lon: float, model: str, index: int = 0) -> WeatherSnapshot:
    def at(key: str):
        values = data.get(key)
        return values[index] if isinstance(values, list) and index < len(values) else None
    ts_ms = at("ts")
    timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat() if ts_ms else datetime.now(timezone.utc).isoformat()
    return WeatherSnapshot(
        timestamp_utc=timestamp, latitude=lat, longitude=lon, provider="Windy", model=model,
        wind_u_mps=at("wind_u-surface"), wind_v_mps=at("wind_v-surface"),
        gust_mps=at("gust-surface"), current_u_mps=at("seacurrents_u-surface"),
        current_v_mps=at("seacurrents_v-surface"), wave_height_m=at("waves_height-surface"),
        wave_period_s=at("waves_period-surface"), wave_direction_deg=at("waves_direction-surface"),
    )
