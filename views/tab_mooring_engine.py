"""Automatic schedule-driven mooring session dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from config.constants import PORT_COORDINATES
from core.mooring_session import EnvironmentalObservation
from core.schedule_runtime import reconcile_schedule
from core.windy_point_forecast import WindyPointForecastError, fetch_forecast
from database.db_manager import get_line_history
from database.mooring_session_repository import add_environment


WINDY_REFRESH_MINUTES = 30


def _windy_api_key() -> str | None:
    """Read the secret without ever displaying it or storing it in Git."""
    try:
        value = st.secrets.get("WINDY_POINT_FORECAST_API_KEY")
    except Exception:
        value = None
    if value:
        return str(value).strip()
    return None


def _fetch_windy_for_port(port_name: str):
    coords = PORT_COORDINATES.get(port_name)
    if not coords:
        raise WindyPointForecastError(f"No coordinates configured for port: {port_name}")
    api_key = _windy_api_key()
    if not api_key:
        raise WindyPointForecastError(
            "WINDY_POINT_FORECAST_API_KEY is not configured in Streamlit Secrets."
        )
    return fetch_forecast(api_key, coords["lat"], coords["lon"], include_marine=True)


def _maybe_refresh_environment(port_name: str):
    """Refresh forecast at most every 30 minutes for the current browser session."""
    now = datetime.now(timezone.utc)
    state = st.session_state.get("windy_environment")
    if state and state.get("port") == port_name:
        last_fetch = state.get("fetched_at")
        if isinstance(last_fetch, datetime) and now - last_fetch < timedelta(minutes=WINDY_REFRESH_MINUTES):
            return state.get("result")

    result = _fetch_windy_for_port(port_name)
    st.session_state["windy_environment"] = {
        "port": port_name,
        "fetched_at": now,
        "result": result,
    }
    return result


def _persist_environment(session, result) -> bool:
    if not session or session.status.value != "ACTIVE" or result.observation is None:
        return False
    obs = result.observation
    observation = EnvironmentalObservation(
        timestamp_utc=obs.timestamp_utc.isoformat(),
        wind_speed_mps=obs.wind_speed_mps,
        wind_direction_deg=obs.wind_direction_from_deg_true,
        gust_mps=obs.gust_speed_mps,
        current_speed_mps=obs.current_speed_mps,
        current_direction_deg=obs.current_direction_to_deg_true,
        wave_height_m=obs.wave_height_m,
        wave_period_s=obs.wave_period_s,
        provider=obs.provider,
        source_kind=obs.source_kind,
        forecast_reference_time=None,
        tidal_current_u_mps=obs.tidal_current_u_mps,
        tidal_current_v_mps=obs.tidal_current_v_mps,
        water_level_m=None,
        water_level_datum=None,
    )
    return add_environment(session.session_id, observation)


def _render_environment(session, port_name: str) -> None:
    st.subheader("🌐 Environmental Input — Windy Point Forecast")
    try:
        result = _maybe_refresh_environment(port_name)
    except WindyPointForecastError as exc:
        st.warning(f"⚠️ Environmental forecast unavailable: {exc}")
        return
    except Exception as exc:
        st.error(f"Unexpected Windy integration error: {exc}")
        return

    obs = result.observation
    if obs is None:
        st.warning("Windy returned no usable environmental observation.")
        return

    persisted = _persist_environment(session, result)
    if persisted:
        st.caption(f"Environmental observation saved: {obs.timestamp_utc.isoformat()}")
    elif session.status.value != "ACTIVE":
        st.caption("Preview for the scheduled call — database persistence starts when the mooring session becomes ACTIVE.")

    c = st.columns(7)
    c[0].metric("Wind", f"{obs.wind_speed_mps:.1f} m/s" if obs.wind_speed_mps is not None else "N/A")
    c[1].metric("Wind from", f"{obs.wind_direction_from_deg_true:.0f}°" if obs.wind_direction_from_deg_true is not None else "N/A")
    c[2].metric("Gust", f"{obs.gust_speed_mps:.1f} m/s" if obs.gust_speed_mps is not None else "N/A")
    c[3].metric("Current", f"{obs.current_speed_mps:.2f} m/s" if obs.current_speed_mps is not None else "N/A")
    c[4].metric("Current to", f"{obs.current_direction_to_deg_true:.0f}°" if obs.current_direction_to_deg_true is not None else "N/A")
    c[5].metric("Wave H", f"{obs.wave_height_m:.2f} m" if obs.wave_height_m is not None else "N/A")
    c[6].metric("Wave T", f"{obs.wave_period_s:.1f} s" if obs.wave_period_s is not None else "N/A")

    st.caption(
        f"Forecast timestamp: {obs.timestamp_utc.isoformat()} | "
        f"Source: {obs.provider} / {obs.source_kind}"
    )

    if obs.tidal_current_u_mps is not None and obs.tidal_current_v_mps is not None:
        st.caption(
            f"Tidal-current vector: U={obs.tidal_current_u_mps:.3f} m/s, "
            f"V={obs.tidal_current_v_mps:.3f} m/s"
        )
    else:
        st.info(
            "Tidal current was not returned by the configured Windy model/key. "
            "No tidal-current value is being fabricated."
        )

    st.info(
        "Water level / tide height is intentionally not populated from Windy: "
        "Point Forecast provides tidal-current vectors, not tide height. "
        "A separate tide source will be connected before tide-driven geometry is used."
    )

    if result.warnings:
        with st.expander("Windy source diagnostics"):
            for warning in result.warnings:
                st.write(f"• {warning}")
            st.write("Model status:", result.model_status)


def render_tab_mooring_engine():
    st.header("⚡ Automatic Mooring Session Management")

    @st.fragment(run_every="60s")
    def scheduler_fragment():
        result = reconcile_schedule(st.session_state.get("port_schedule", pd.DataFrame()))
        st.session_state["mooring_runtime"] = result
        if result.get("status") == "IN_TRANSIT":
            st.info("⚓ No active port call in the calendar. Monitoring is standing by automatically.")
            return
        session = result.get("session")
        if result.get("operator"):
            st.warning("⚠️ Calendar or mooring setup changed. The existing active record is preserved; operator review is required.")
        if session:
            c = st.columns(5)
            c[0].metric("Port", session.port_name)
            c[1].metric("Session", session.session_id)
            c[2].metric("Status", session.status.value)
            c[3].metric("Setup", session.setup_name or "N/A")
            c[4].metric("Source", session.setup_source)
            st.caption(f"Scheduled: {session.scheduled_start_utc} → {session.scheduled_end_utc}")

            if not result.get("operator"):
                _render_environment(session, session.port_name)

    scheduler_fragment()
    st.divider()
    st.subheader("📚 Line History")
    history = get_line_history()
    if history.empty:
        st.caption("No accumulated line history yet.")
    else:
        st.dataframe(history, use_container_width=True)
