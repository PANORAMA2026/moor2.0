"""Automatic schedule-driven mooring session dashboard."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from config.constants import DEFAULT_SHIP, PORT_COORDINATES
from core.environmental_engine import LegacyCurrentProvider, LegacyWindProvider, VesselHydroGeometry
from core.environmental_state import EnvironmentalState
from core.line_mechanics import calculate_line_geometry
from core.mooring_calculation import run_mooring_calculation
from core.mooring_session import EnvironmentalObservation, LineExposure
from core.schedule_runtime import reconcile_schedule
from core.windy_point_forecast import WindyPointForecastError, fetch_forecast
from database.db_manager import get_line_history, get_port_mooring_setups
from database.mooring_session_repository import add_environment, add_line_exposure


WINDY_REFRESH_MINUTES = 30
CALCULATION_SAMPLE_SECONDS = 60.0


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
    """Persist a forecast observation only once per forecast timestamp."""
    if not session or session.status.value != "ACTIVE" or result.observation is None:
        return False

    obs = result.observation
    key = f"{session.session_id}:{obs.timestamp_utc.isoformat()}"
    if st.session_state.get("last_persisted_environment_key") == key:
        return False

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
    add_environment(session.session_id, observation)
    st.session_state["last_persisted_environment_key"] = key
    return True


def _build_calculation_geometry(session, port_name: str) -> pd.DataFrame:
    inventory = st.session_state.get("lines_inventory", pd.DataFrame())
    if inventory is None or inventory.empty:
        raise ValueError("Line inventory is empty.")

    setups = get_port_mooring_setups(port_name)
    setup_df = setups.get(session.setup_name or "")
    if setup_df is None or setup_df.empty:
        raise ValueError(f"Mooring setup '{session.setup_name}' is not available for {port_name}.")

    line_ids = setup_df["line_id"].astype(str).tolist()
    lines = inventory.copy()
    lines["line_id"] = lines["line_id"].astype(str)
    lines = lines[lines["line_id"].isin(line_ids)].copy()
    if lines.empty:
        raise ValueError("The active mooring setup contains no matching inventory lines.")

    setup_values = setup_df[["line_id", "mbl_percentage"]].copy()
    setup_values["line_id"] = setup_values["line_id"].astype(str)
    setup_values["pretension_pct"] = pd.to_numeric(setup_values["mbl_percentage"], errors="coerce")
    lines = lines.merge(
        setup_values[["line_id", "pretension_pct"]],
        on="line_id",
        how="left",
        validate="one_to_one",
    )
    if lines["pretension_pct"].isna().any():
        raise ValueError("One or more active mooring lines have no valid pretension setting.")

    bollards = st.session_state.get("ports_bollards", {}).get(port_name, pd.DataFrame())
    if bollards is None or bollards.empty:
        raise ValueError(f"No bollard layout is available for {port_name}.")

    required_bollard_columns = {"bollard_id", "bollard_x_m", "bollard_y_m", "bollard_z_m"}
    if not required_bollard_columns.issubset(set(bollards.columns)):
        raise ValueError(
            "Bollard coordinates are incomplete. Engineering tension calculation "
            "requires X/Y/Z coordinates for every used bollard."
        )

    return calculate_line_geometry(
        lines,
        bollards,
        loa=float(DEFAULT_SHIP["LOA"]),
        offset_fugro=float(st.session_state.get("offset_fugro_m", 0.0)),
    )


def _environmental_state_from_result(result) -> EnvironmentalState:
    obs = result.observation
    if obs is None:
        raise ValueError("Windy returned no usable environmental observation.")
    return EnvironmentalState(
        timestamp_utc=obs.timestamp_utc,
        wind_speed_mps=obs.wind_speed_mps,
        wind_direction_from_deg_true=obs.wind_direction_from_deg_true,
        gust_speed_mps=obs.gust_speed_mps,
        current_speed_mps=obs.current_speed_mps,
        current_direction_to_deg_true=obs.current_direction_to_deg_true,
        tidal_current_u_mps=obs.tidal_current_u_mps,
        tidal_current_v_mps=obs.tidal_current_v_mps,
        wave_height_m=obs.wave_height_m,
        wave_period_s=obs.wave_period_s,
        water_level_m=None,
        water_level_datum=None,
        provider=obs.provider,
        source_kind=obs.source_kind,
    )


def _calculate_current_mooring_state(session, port_name: str, result):
    geometry = _build_calculation_geometry(session, port_name)
    environment = _environmental_state_from_result(result)

    loa = float(DEFAULT_SHIP["LOA"])
    beam = float(DEFAULT_SHIP["Beam"])
    draft = float(DEFAULT_SHIP["Draft"])
    vessel = VesselHydroGeometry(
        frontal_wind_area_m2=float(st.session_state.get("afw", DEFAULT_SHIP["AFW"])),
        lateral_wind_area_m2=float(st.session_state.get("alw", DEFAULT_SHIP["ALW"])),
        frontal_submerged_area_m2=beam * draft,
        lateral_submerged_area_m2=float(DEFAULT_SHIP.get("ALC") or loa * draft),
        loa_m=loa,
    )

    berth_heading = float(st.session_state.get("port_headings", {}).get(port_name, 0.0))
    results, loads = run_mooring_calculation(
        geometry,
        environment,
        vessel,
        berth_heading,
        LegacyWindProvider(),
        LegacyCurrentProvider(wd_d_ratio=3.0),
        pretension_pct=None,
    )
    return results, loads, environment


def _persist_line_exposure(session, results: pd.DataFrame, environment: EnvironmentalState) -> int:
    if not session or session.status.value != "ACTIVE" or results.empty:
        return 0

    now = datetime.now(timezone.utc)
    last_sample = st.session_state.get("last_line_exposure_at")
    if isinstance(last_sample, datetime) and last_sample.tzinfo is None:
        last_sample = last_sample.replace(tzinfo=timezone.utc)

    duration_s = CALCULATION_SAMPLE_SECONDS
    if isinstance(last_sample, datetime):
        elapsed = (now - last_sample).total_seconds()
        if 0.0 < elapsed <= 300.0:
            duration_s = elapsed

    count = 0
    for _, row in results.iterrows():
        tension = row.get("Tension_tons")
        util = row.get("Util_Percent")
        mbl = row.get("mbl_tons")
        if pd.isna(tension) or pd.isna(util) or pd.isna(mbl):
            continue
        exposure = LineExposure(
            line_id=str(row.get("line_id")),
            timestamp_utc=now.isoformat(),
            tension_n=float(tension) * 1000.0 * 9.80665,
            mbl_n=float(mbl) * 1000.0 * 9.80665,
            utilization_pct=float(util),
            duration_s=duration_s,
            source="SOLVER_FORECAST",
            valid=True,
            diagnostic=(
                "Forecast-based static equilibrium; not a measured line load. "
                f"Environmental forecast timestamp={environment.timestamp_utc.isoformat()}"
            ),
        )
        add_line_exposure(session.session_id, exposure)
        count += 1

    if count:
        st.session_state["last_line_exposure_at"] = now
    return count


def _render_environment_and_calculation(session, port_name: str) -> None:
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

    if _persist_environment(session, result):
        st.caption(f"Environmental observation saved: {obs.timestamp_utc.isoformat()}")

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
            "Tidal current is not available from the current Windy API key/model. "
            "No tidal-current value is being fabricated."
        )

    st.info(
        "Water level / tide height is not populated from Windy. "
        "Tide-driven vertical geometry will remain inactive until a separate "
        "water-level source is connected."
    )

    if result.warnings:
        with st.expander("Windy source diagnostics"):
            for warning in result.warnings:
                st.write(f"• {warning}")
            st.write("Model status:", result.model_status)

    st.divider()
    st.subheader("🧮 Engineering Mooring Calculation")
    try:
        results, loads, environment = _calculate_current_mooring_state(session, port_name, result)
    except Exception as exc:
        st.warning(f"⚠️ Tension calculation not available: {exc}")
        st.caption(
            "The calculation is intentionally blocked when required engineering "
            "geometry or line/setup data are missing; no synthetic geometry or load is substituted."
        )
        return

    st.session_state["latest_mooring_results"] = results
    st.session_state["latest_mooring_loads"] = loads
    st.session_state["latest_mooring_environment"] = environment

    diagnostics = results.attrs.get("solver_diagnostics")
    if diagnostics is not None:
        st.caption(
            f"Solver: {diagnostics.status.value} | iterations={diagnostics.iterations} | "
            f"residual={diagnostics.residual_norm:.6g}"
        )

    load_cols = st.columns(3)
    load_cols[0].metric("Fx", f"{loads.total.fx_n / 9806.65:.2f} t")
    load_cols[1].metric("Fy", f"{loads.total.fy_n / 9806.65:.2f} t")
    load_cols[2].metric("Mz", f"{loads.total.mz_nm / 9806.65:.2f} t·m")

    display_cols = [
        c for c in [
            "line_id", "line_name", "bollard_id", "length_m", "azimuth_deg",
            "incline_deg", "Pretension_Percent", "Tension_tons", "Util_Percent",
            "Solver_Status", "Residual_Norm",
        ] if c in results.columns
    ]
    st.dataframe(results[display_cols], use_container_width=True)

    exposure_count = _persist_line_exposure(session, results, environment)
    if exposure_count:
        st.caption(f"Saved {exposure_count} forecast-based line exposure samples to session history.")

    st.warning(
        "Engineering status: this is a deterministic environmental-load/equilibrium calculation. "
        "Line stiffness still uses the project's compatibility fallback when certified load-extension "
        "curves are not yet attached to the line certificate. It must not be represented as class-approved analysis."
    )


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
            st.warning(
                "⚠️ Calendar or mooring setup changed. The existing active record is preserved; "
                "operator review is required."
            )
        if session:
            c = st.columns(5)
            c[0].metric("Port", session.port_name)
            c[1].metric("Session", session.session_id)
            c[2].metric("Status", session.status.value)
            c[3].metric("Setup", session.setup_name or "N/A")
            c[4].metric("Source", session.setup_source)
            st.caption(f"Scheduled: {session.scheduled_start_utc} → {session.scheduled_end_utc}")

            if not result.get("operator") and session.status.value == "ACTIVE":
                _render_environment_and_calculation(session, session.port_name)

    scheduler_fragment()
    st.divider()
    st.subheader("📚 Line History")
    history = get_line_history()
    if history.empty:
        st.caption("No accumulated line history yet.")
    else:
        st.dataframe(history, use_container_width=True)
