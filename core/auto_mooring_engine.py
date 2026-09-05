"""
core/auto_mooring_engine.py
Automatic mooring-session tracking with 30-minute sampling and a wind-change
trigger. Environmental data must come from a real source or an explicit
operator override; no simulated weather values are used.
"""

from datetime import datetime
import requests
import pandas as pd
import streamlit as st
from config.constants import PORT_COORDINATES
from database.db_manager import get_line_history, save_line_history, get_port_mooring_setups


WIND_CHANGE_TRIGGER_KTS = 6.0
LOG_INTERVAL_HOURS = 0.5
WEATHER_TIMEOUT_SECONDS = 5


def fetch_live_weather(port_name: str) -> dict:
    """Retrieve current wind from Open-Meteo for the selected port."""
    coords = PORT_COORDINATES.get(port_name)
    if not coords:
        return {"available": False, "wind_speed_kts": None, "wind_dir_deg": None, "status": "Weather source unavailable"}

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": coords["lat"],
                "longitude": coords["lon"],
                "current": "wind_speed_10m,wind_direction_10m",
                "wind_speed_unit": "kn",
            },
            timeout=WEATHER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        current = response.json().get("current", {})
        speed = current.get("wind_speed_10m")
        direction = current.get("wind_direction_10m")
        if speed is None or direction is None:
            raise ValueError("Open-Meteo returned incomplete current wind data")
        return {
            "available": True,
            "wind_speed_kts": float(speed),
            "wind_dir_deg": float(direction),
            "status": "Open-Meteo Live",
        }
    except Exception as exc:
        return {
            "available": False,
            "wind_speed_kts": None,
            "wind_dir_deg": None,
            "status": f"Weather unavailable: {exc}",
        }


def process_automatic_mooring_logging():
    """
    Manage the active mooring session between ETA and ETD.

    Logging occurs every 30 minutes or when wind changes by at least 6 knots.
    If live weather is unavailable, the engine does not invent a value and does
    not write a false automatic measurement. An explicit operator weather
    override remains supported.
    """
    if "port_schedule" not in st.session_state or st.session_state["port_schedule"].empty:
        return {"status": "NO_SCHEDULE", "message": "Nessun calendario caricato."}

    now = datetime.now()
    df_schedule = st.session_state["port_schedule"]
    active_port = df_schedule[(df_schedule["ETA"] <= now) & (df_schedule["ETD"] >= now)]

    if active_port.empty:
        if "active_mooring_session" in st.session_state:
            del st.session_state["active_mooring_session"]
        return {"status": "IN_TRANSIT", "message": "Nave in navigazione. Nessun ormeggio attivo."}

    row = active_port.iloc[0]
    port_name = str(row["Port"])
    eta = row["ETA"]
    etd = row["ETD"]

    session_key = f"session_{port_name}_{eta.strftime('%Y%m%d_%H%M')}"
    if "active_mooring_session" not in st.session_state or st.session_state["active_mooring_session"].get("id") != session_key:
        st.session_state["active_mooring_session"] = {
            "id": session_key,
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "last_sync_time": now,
            "last_logged_wind": None,
            "accumulated_interval_hours": 0.0,
        }

    session = st.session_state["active_mooring_session"]

    weather_override_key = f"weather_override_{port_name}"
    if weather_override_key in st.session_state:
        current_wind = float(st.session_state[weather_override_key]["wind_speed"])
        weather_src = "Manuale Operatore"
        weather_available = True
    else:
        weather_info = fetch_live_weather(port_name)
        current_wind = weather_info["wind_speed_kts"]
        weather_src = weather_info["status"]
        weather_available = bool(weather_info["available"])

    if not weather_available:
        return {
            "status": "WEATHER_UNAVAILABLE",
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "hours_in_port": (now - eta).total_seconds() / 3600.0,
            "current_wind": None,
            "last_logged_wind": session["last_logged_wind"],
            "weather_src": weather_src,
            "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
            "last_trigger": "Waiting for valid weather data",
            "summary": pd.DataFrame(),
        }

    time_since_last_sync = (now - session["last_sync_time"]).total_seconds() / 3600.0
    last_wind = session["last_logged_wind"]
    is_interval_passed = time_since_last_sync >= LOG_INTERVAL_HOURS
    is_wind_event = last_wind is not None and abs(current_wind - last_wind) >= WIND_CHANGE_TRIGGER_KTS

    if last_wind is None:
        session["last_logged_wind"] = current_wind
        session["last_sync_time"] = now
        return {
            "status": "IN_PORT",
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "hours_in_port": (now - eta).total_seconds() / 3600.0,
            "current_wind": current_wind,
            "last_logged_wind": session["last_logged_wind"],
            "weather_src": weather_src,
            "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
            "last_trigger": "Initial weather reference recorded",
            "summary": pd.DataFrame(),
        }

    trigger_reason = None
    if is_interval_passed:
        trigger_reason = "Interval 30 min"
    elif is_wind_event:
        trigger_reason = f"Wind Delta ({current_wind - last_wind:+.1f} kts)"

    auto_summary_df = pd.DataFrame()

    if trigger_reason:
        interval_hours = max(0.1, round(time_since_last_sync, 2))
        available_setups = get_port_mooring_setups(port_name)
        override_key = f"override_setup_{port_name}"
        if override_key in st.session_state and st.session_state[override_key] in available_setups:
            selected_setup_name = st.session_state[override_key]
        else:
            selected_setup_name = list(available_setups.keys())[0] if available_setups else "Default Standard"

        setup_df = available_setups.get(selected_setup_name, pd.DataFrame())
        lines_df = get_line_history()
        # This factor is retained only as the legacy accumulated-stress estimate.
        # It is not presented as a calculated line tension.
        weather_factor = 1.0 + (current_wind / 50.0)

        updated_records = []
        if not setup_df.empty:
            for _, s_row in setup_df.iterrows():
                l_id = str(s_row.get("line_id", ""))
                base_mbl = float(s_row.get("mbl_percentage", 15.0))
                calc_tension = min(100.0, base_mbl * weather_factor)

                prev_hours, prev_stress = 0.0, 0.0
                if not lines_df.empty and "line_id" in lines_df.columns:
                    match = lines_df[lines_df["line_id"].astype(str) == l_id]
                    if not match.empty:
                        prev_hours = float(match.iloc[0].get("total_hours", 0.0))
                        prev_stress = float(match.iloc[0].get("accumulated_stress_index", 0.0))

                updated_records.append({
                    "line_id": l_id,
                    "last_port": port_name,
                    "current_setup": selected_setup_name,
                    "applied_tension_mbl_pct": round(calc_tension, 2),
                    "interval_hours": interval_hours,
                    "total_hours": round(prev_hours + interval_hours, 2),
                    "accumulated_stress_index": round(prev_stress + (calc_tension * interval_hours), 2),
                    "trigger_event": trigger_reason,
                    "last_auto_sync": now.strftime("%Y-%m-%d %H:%M:%S"),
                })

            auto_summary_df = pd.DataFrame(updated_records)
            save_line_history(auto_summary_df)

        session["last_sync_time"] = now
        session["last_logged_wind"] = current_wind
        session["accumulated_interval_hours"] += interval_hours

    return {
        "status": "IN_PORT",
        "port": port_name,
        "eta": eta,
        "etd": etd,
        "hours_in_port": (now - eta).total_seconds() / 3600.0,
        "current_wind": current_wind,
        "last_logged_wind": session["last_logged_wind"],
        "weather_src": weather_src,
        "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
        "last_trigger": trigger_reason if trigger_reason else "Monitoring...",
        "summary": auto_summary_df,
    }
