"""Adapters for external tide/current data sources.

Adapters normalize external data into ``TidalState``. They do not decide whether
an external source is suitable for engineering use; source suitability remains a
configuration/verification decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.tidal_models import TidalState


def _utc_from_ms(timestamp_ms: int | float) -> datetime:
    return datetime.fromtimestamp(float(timestamp_ms) / 1000.0, tz=timezone.utc)


def parse_windy_tidal_current(
    timestamp_ms: int | float,
    payload: dict[str, Any],
    source: str = "WINDY_POINT_FORECAST",
) -> TidalState:
    """Normalize Windy ``currentsTide`` u/v components.

    Windy documents u as West->East and v as South->North. The function accepts
    the response values after the API's parameter naming has been normalized.
    It intentionally does not fabricate water level from current data.
    """
    u = payload.get("seacurrents_tide_u-surface")
    v = payload.get("seacurrents_tide_v-surface")
    return TidalState(
        timestamp_utc=_utc_from_ms(timestamp_ms),
        tidal_current_u_mps=None if u is None else float(u),
        tidal_current_v_mps=None if v is None else float(v),
        source=source,
        source_kind="FORECAST",
    )


def parse_tide_height(
    timestamp_utc: datetime,
    height_m: float,
    datum: str,
    source: str,
    source_kind: str,
) -> TidalState:
    """Normalize a tide-height observation/prediction with explicit datum."""
    if timestamp_utc.tzinfo is None:
        timestamp_utc = timestamp_utc.replace(tzinfo=timezone.utc)
    else:
        timestamp_utc = timestamp_utc.astimezone(timezone.utc)
    return TidalState(
        timestamp_utc=timestamp_utc,
        water_level_m=float(height_m),
        datum=str(datum),
        source=str(source),
        source_kind=str(source_kind),
    )
