"""Windy Point Forecast API client.

This module deliberately contains no Streamlit state. API credentials are supplied
by the application layer and are never persisted by this client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, degrees, hypot
from typing import Any

import requests

WINDY_POINT_FORECAST_URL = "https://api.windy.com/api/point-forecast/v2"


@dataclass(frozen=True)
class WindyObservation:
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
    wave_direction_from_deg_true: float | None = None
    provider: str = "WINDY_POINT_FORECAST"
    source_kind: str = "FORECAST"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class WindyForecastResult:
    observation: WindyObservation | None
    latitude: float
    longitude: float
    model_status: dict[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class WindyPointForecastError(RuntimeError):
    """Raised for configuration, transport, or API response errors."""


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _vector_speed_direction_to(u: Any, v: Any) -> tuple[float | None, float | None]:
    u_f, v_f = _finite(u), _finite(v)
    if u_f is None or v_f is None:
        return None, None
    speed = hypot(u_f, v_f)
    if speed <= 1e-12:
        return 0.0, None
    # Windy u/v are geographic east/north components. atan2(u, v)
    # therefore gives a compass bearing toward which the vector points.
    direction_to = (degrees(atan2(u_f, v_f)) + 360.0) % 360.0
    return speed, direction_to


def _wind_from_direction(u: Any, v: Any) -> tuple[float | None, float | None]:
    speed, direction_to = _vector_speed_direction_to(u, v)
    if direction_to is None:
        return speed, None
    return speed, (direction_to + 180.0) % 360.0


def _timestamp_series(payload: dict[str, Any]) -> list[datetime]:
    timestamps = payload.get("ts") or []
    result: list[datetime] = []
    for ts in timestamps:
        try:
            result.append(datetime.fromtimestamp(float(ts) / 1000.0, tz=timezone.utc))
        except (TypeError, ValueError, OSError):
            result.append(datetime.min.replace(tzinfo=timezone.utc))
    return result


def _at(payload: dict[str, Any], key: str, index: int) -> Any:
    values = payload.get(key)
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def _request(
    api_key: str,
    latitude: float,
    longitude: float,
    model: str,
    parameters: list[str],
    timeout_s: float,
) -> tuple[int, dict[str, Any] | None, str | None]:
    body = {
        "lat": round(float(latitude), 2),
        "lon": round(float(longitude), 2),
        "model": model,
        "parameters": parameters,
        "levels": ["surface"],
        "key": api_key,
    }
    try:
        response = requests.post(WINDY_POINT_FORECAST_URL, json=body, timeout=timeout_s)
    except requests.RequestException as exc:
        return 0, None, f"Transport error: {exc}"

    if response.status_code == 204:
        return 204, None, f"Model {model} returned no requested data (HTTP 204)."
    if response.status_code != 200:
        detail = response.text.strip()[:300]
        return response.status_code, None, f"Windy {model} request failed (HTTP {response.status_code}): {detail}"
    try:
        return 200, response.json(), None
    except ValueError:
        return 200, None, f"Windy {model} returned invalid JSON."


def fetch_forecast(
    api_key: str,
    latitude: float,
    longitude: float,
    *,
    at_utc: datetime | None = None,
    timeout_s: float = 15.0,
    include_marine: bool = True,
) -> WindyForecastResult:
    """Fetch the closest forecast point to *at_utc*.

    Wind, gust, waves, total current and tidal-current data are requested from
    the Windy models that expose them. Marine models may be unavailable on a
    testing key; that is recorded as a warning rather than fabricating values.
    Windy Point Forecast does not provide tide height, so water level remains
    unavailable here and must come from a separate tide source.
    """
    if not api_key or not api_key.strip():
        raise WindyPointForecastError("Windy Point Forecast API key is not configured.")
    target = at_utc or datetime.now(timezone.utc)
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    target = target.astimezone(timezone.utc)

    model_payloads: dict[str, dict[str, Any]] = {}
    statuses: dict[str, str] = {}
    warnings: list[str] = []

    requests_to_make = [
        ("gfs", ["wind", "windGust"]),
    ]
    if include_marine:
        requests_to_make.extend([
            ("gfsWave", ["waves"]),
            ("cmems", ["currents", "currentsTide"]),
        ])

    for model, parameters in requests_to_make:
        status, payload, error = _request(api_key, latitude, longitude, model, parameters, timeout_s)
        statuses[model] = str(status)
        if payload is not None:
            model_payloads[model] = payload
        elif error:
            warnings.append(error)

    if "gfs" not in model_payloads:
        raise WindyPointForecastError("Wind forecast could not be obtained. " + " | ".join(warnings))

    gfs = model_payloads["gfs"]
    ts = _timestamp_series(gfs)
    if not ts:
        raise WindyPointForecastError("Windy GFS response contains no forecast timestamps.")
    index = min(range(len(ts)), key=lambda i: abs((ts[i] - target).total_seconds()))

    wind_speed, wind_from = _wind_from_direction(_at(gfs, "wind_u-surface", index), _at(gfs, "wind_v-surface", index))
    gust = _finite(_at(gfs, "gust-surface", index))

    wave_height = wave_period = wave_direction = None
    if "gfsWave" in model_payloads:
        wave = model_payloads["gfsWave"]
        wave_ts = _timestamp_series(wave)
        if wave_ts:
            wi = min(range(len(wave_ts)), key=lambda i: abs((wave_ts[i] - target).total_seconds()))
            wave_height = _finite(_at(wave, "waves_height-surface", wi))
            wave_period = _finite(_at(wave, "waves_period-surface", wi))
            wave_direction = _finite(_at(wave, "waves_direction-surface", wi))

    current_speed = current_direction = tidal_u = tidal_v = None
    if "cmems" in model_payloads:
        cmems = model_payloads["cmems"]
        current_ts = _timestamp_series(cmems)
        if current_ts:
            ci = min(range(len(current_ts)), key=lambda i: abs((current_ts[i] - target).total_seconds()))
            cu = _finite(_at(cmems, "seacurrents_u-surface", ci))
            cv = _finite(_at(cmems, "seacurrents_v-surface", ci))
            current_speed, current_direction = _vector_speed_direction_to(cu, cv)
            tidal_u = _finite(_at(cmems, "seacurrents_tide_u-surface", ci))
            tidal_v = _finite(_at(cmems, "seacurrents_tide_v-surface", ci))

    observation = WindyObservation(
        timestamp_utc=ts[index],
        wind_speed_mps=wind_speed,
        wind_direction_from_deg_true=wind_from,
        gust_speed_mps=gust,
        current_speed_mps=current_speed,
        current_direction_to_deg_true=current_direction,
        tidal_current_u_mps=tidal_u,
        tidal_current_v_mps=tidal_v,
        wave_height_m=wave_height,
        wave_period_s=wave_period,
        wave_direction_from_deg_true=wave_direction,
        warnings=tuple(warnings),
    )
    return WindyForecastResult(observation, float(latitude), float(longitude), statuses, tuple(warnings))
