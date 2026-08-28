"""
services/auto_mooring_engine.py
Motore di tracciamento automatico ormeggio con intervallo di 30 minuti 
dall'ETA all'ETD e salvataggio immediato su variazione vento >= +-6 kts.
"""

from datetime import datetime
import pandas as pd
import streamlit as st
from database.db_manager import get_line_history, save_line_history, get_port_mooring_setups


def fetch_live_weather(port_name: str) -> dict:
    """Recupera la velocità e direzione del vento per il porto corrente."""
    # Sostituire con chiamata API meteo reale (es. OpenWeatherMap / Meteo API)
    return {"wind_speed_kts": 18.5, "wind_dir_deg": 45, "status": "Live API"}


def process_automatic_mooring_logging():
    """
    Gestisce la sessione d'ormeggio tra ETA ed ETD:
    - Avvia la sessione al contatto col porto.
    - Esegue il salvataggio automatico ogni 30 minuti (0.5h).
    - Forza il salvataggio immediato se il vento varia di +-6 nodi.
    - Chiude e salva la sessione all'ETD.
    """
    if "port_schedule" not in st.session_state or st.session_state["port_schedule"].empty:
        return {"status": "NO_SCHEDULE", "message": "Nessun calendario caricato."}

    now = datetime.now()
    df_schedule = st.session_state["port_schedule"]

    # 1. IDENTIFICAZIONE PORTO ATTIVO (FINESTRA ETA - ETD)
    active_port = df_schedule[(df_schedule["ETA"] <= now) & (df_schedule["ETD"] >= now)]

    if active_port.empty:
        # Se siamo fuori finestra, azzera la sessione precedente
        if "active_mooring_session" in st.session_state:
            del st.session_state["active_mooring_session"]
        return {"status": "IN_TRANSIT", "message": "Nave in navigazione. Nessun ormeggio attivo."}

    row = active_port.iloc[0]
    port_name = str(row["Port"])
    eta = row["ETA"]
    etd = row["ETD"]

    # 2. INIZIALIZZAZIONE SESSIONE DI ORMEGGIO AL CONTATTO COL PORTO
    session_key = f"session_{port_name}_{eta.strftime('%Y%m%d_%H%M')}"
    if "active_mooring_session" not in st.session_state or st.session_state["active_mooring_session"].get("id") != session_key:
        st.session_state["active_mooring_session"] = {
            "id": session_key,
            "port": port_name,
            "eta": eta,
            "etd": etd,
            "last_sync_time": now,
            "last_logged_wind": None,
            "accumulated_interval_hours": 0.0
        }

    session = st.session_state["active_mooring_session"]

    # 3. LETTURA METEO LIVE O OVERRIDE
    weather_override_key = f"weather_override_{port_name}"
    if weather_override_key in st.session_state:
        current_wind = float(st.session_state[weather_override_key]["wind_speed"])
        weather_src = "Manuale Operatore"
    else:
        weather_info = fetch_live_weather(port_name)
        current_wind = float(weather_info["wind_speed_kts"])
        weather_src = weather_info["status"]

    # 4. VALUTAZIONE TRIGGER DI SALVATAGGIO (30 MINUTI O VARIAZIONE VENTO +-6 KTS)
    time_since_last_sync = (now - session["last_sync_time"]).total_seconds() / 3600.0  # ore trascorse
    last_wind = session["last_logged_wind"]

    # Condizione A: Trascorsi 30 minuti (0.5 ore) dall'ultimo salvataggio
    is_30min_passed = time_since_last_sync >= 0.5

    # Condizione B: Variazione del vento >= +-6 nodi
    is_wind_event = False
    if last_wind is not None:
        wind_delta = abs(current_wind - last_wind)
        if wind_delta >= 6.0:
            is_wind_event = True

    # Primo avvio della sessione: registra il vento iniziale
    if last_wind is None:
        session["last_logged_wind"] = current_wind
        session["last_sync_time"] = now

    # Se scatta uno dei due trigger, procediamo al salvataggio automatico
    trigger_reason = None
    if is_30min_passed:
        trigger_reason = "Interval 30 min"
    elif is_wind_event:
        trigger_reason = f"Wind Delta ({current_wind - last_wind:+.1f} kts)"

    auto_summary_df = pd.DataFrame()

    if trigger_reason:
        # Calcolo intervallo effettivo da registrare
        interval_hours = max(0.1, round(time_since_last_sync, 2))

        # Recupero Setup di Ormeggio
        available_setups = get_port_mooring_setups(port_name)
        override_key = f"override_setup_{port_name}"
        if override_key in st.session_state and st.session_state[override_key] in available_setups:
            selected_setup_name = st.session_state[override_key]
        else:
            selected_setup_name = list(available_setups.keys())[0] if available_setups else "Default Standard"

        setup_df = available_setups.get(selected_setup_name, pd.DataFrame())
        lines_df = get_line_history()
        weather_factor = 1.0 + (current_wind / 50.0)

        updated_records = []
        if not setup_df.empty:
            for _, s_row in setup_df.iterrows():
                l_id = str(s_row.get("line_id", ""))
                base_mbl = float(s_row.get("mbl_percentage", 15.0))
                calc_tension = min(100.0, base_mbl * weather_factor)

                prev_hours, prev_stress = 0.0, 0.0
                if not lines_df.empty and "line_id" in lines_df.columns:
                    match = lines_df[lines_df["line_id"] == l_id]
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
                    "last_auto_sync": now.strftime("%Y-%m-%d %H:%M:%S")
                })

            auto_summary_df = pd.DataFrame(updated_records)
            save_line_history(auto_summary_df)

        # Aggiornamento stato sessione
        session["last_sync_time"] = now
        session["last_logged_wind"] = current_wind
        session["accumulated_interval_hours"] += interval_hours

    total_hours_in_port = (now - eta).total_seconds() / 3600.0

    return {
        "status": "IN_PORT",
        "port": port_name,
        "eta": eta,
        "etd": etd,
        "hours_in_port": total_hours_in_port,
        "current_wind": current_wind,
        "last_logged_wind": session["last_logged_wind"],
        "weather_src": weather_src,
        "last_sync_time": session["last_sync_time"].strftime("%H:%M:%S"),
        "last_trigger": trigger_reason if trigger_reason else "Monitoring...",
        "summary": auto_summary_df
    }
