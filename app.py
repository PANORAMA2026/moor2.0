"""OpenMooring MEG4 Pro — Carnival Panorama."""
from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.constants import DB_FILE_PATH, DEFAULT_SHIP, PORT_COORDINATES
from core.auth import require_login, logout_button
from core.calendar_manager import calendar_state, clear_calendar_storage, persist_calendar
from core.hydrodynamic_forces import calculate_environmental_forces
from core.line_mechanics import calculate_line_geometry, solve_line_tensions_3d
from core.schedule_runtime import reconcile_schedule
from database.db_manager import (
    init_db,
    log_mooring_session,
    load_certificates_from_db,
    load_lines_inventory_from_db,
    load_port_bollards_from_db,
    save_certificate_to_db,
    save_lines_inventory_to_db,
)
from views.tab_berth import render_tab_berth
from views.tab_certificate import render_tab_certificate
from views.tab_history import render_tab_history
from views.tab_plans import render_tab_plans
from views.tab_polar import render_tab_polar
from views.tab_mooring_engine import render_tab_mooring_engine

st.set_page_config(page_title="OpenMooring MEG4 Pro — Carnival Panorama", layout="wide")
require_login()
init_db()
logout_button()

st.session_state.setdefault("afw", DEFAULT_SHIP.get("AFW", 2100.0))
st.session_state.setdefault("alw", DEFAULT_SHIP.get("ALW", 9500.0))
st.session_state.setdefault("alc", DEFAULT_SHIP.get("ALC", 1800.0))
st.session_state.setdefault("loa", DEFAULT_SHIP.get("LOA", 323.44))
st.session_state.setdefault("offset_fugro_m", 0.0)

if "certificates_db" not in st.session_state:
    certs = load_certificates_from_db()
    if certs.empty:
        for cert in [
            {"cert_id": "CERT-HMPE-2025-01", "manufacturer": "Samson Rope", "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "standard": "MEG4 / DNV", "issue_date": "2025-01-15"},
            {"cert_id": "CERT-HMPE-2025-02", "manufacturer": "Katradis", "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "standard": "MEG4 / LRS", "issue_date": "2025-02-10"},
        ]:
            save_certificate_to_db(cert)
        certs = load_certificates_from_db()
    st.session_state["certificates_db"] = certs

if "lines_inventory" not in st.session_state:
    lines = load_lines_inventory_from_db()
    if lines.empty:
        lines = pd.DataFrame([
            {"line_id": "1", "line_name": "Head Line 1", "line_type": "Head", "station_id": "Prua (Forward Station)", "winch_id": "W1", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": 155.0, "chock_y_m": 2.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64.0, "E_modulus_GPa": 120.0, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72.0, "tail_E_modulus_GPa": 6.0, "tail_mbl_tons": 100.0, "bollard_id": "B1"},
            {"line_id": "2", "line_name": "Head Line 2", "line_type": "Head", "station_id": "Prua (Forward Station)", "winch_id": "W2", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": 155.0, "chock_y_m": -2.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72.0, "tail_E_modulus_GPa": 6.0, "tail_mbl_tons": 100.0, "bollard_id": "B1"},
            {"line_id": "3", "line_name": "Fwd Breast 1", "line_type": "Fwd Breast", "station_id": "Prua (Forward Station)", "winch_id": "W3", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": 140.0, "chock_y_m": 18.0, "chock_z_m": 10.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72.0, "tail_E_modulus_GPa": 6.0, "tail_mbl_tons": 100.0, "bollard_id": "B2"},
            {"line_id": "4", "line_name": "Fwd Spring 1", "line_type": "Fwd Spring", "station_id": "Prua (Forward Station)", "winch_id": "W4", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": 110.0, "chock_y_m": 18.0, "chock_z_m": 8.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 0.0, "tail_diameter_mm": 0.0, "tail_E_modulus_GPa": 0.0, "tail_mbl_tons": 0.0, "bollard_id": "B3"},
            {"line_id": "5", "line_name": "Aft Spring 1", "line_type": "Aft Spring", "station_id": "Poppa (Aft Station)", "winch_id": "W5", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": -110.0, "chock_y_m": 18.0, "chock_z_m": 8.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 0.0, "tail_diameter_mm": 0.0, "tail_E_modulus_GPa": 0.0, "tail_mbl_tons": 0.0, "tail_mbl_tons": 0.0, "bollard_id": "B4"},
            {"line_id": "6", "line_name": "Aft Breast 1", "line_type": "Aft Breast", "station_id": "Poppa (Aft Station)", "winch_id": "W6", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": -140.0, "chock_y_m": 18.0, "chock_z_m": 10.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72.0, "tail_E_modulus_GPa": 6.0, "tail_mbl_tons": 100.0, "bollard_id": "B5"},
            {"line_id": "7", "line_name": "Stern Line 1", "line_type": "Stern", "station_id": "Poppa (Aft Station)", "winch_id": "W7", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": -155.0, "chock_y_m": 0.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72.0, "tail_E_modulus_GPa": 6.0, "tail_mbl_tons": 100.0, "bollard_id": "B5"},
        ])
        save_lines_inventory_to_db(lines)
        lines = load_lines_inventory_from_db()
    st.session_state["lines_inventory"] = lines

if "ports_bollards" not in st.session_state:
    st.session_state["ports_bollards"] = {port: load_port_bollards_from_db(port) for port in PORT_COORDINATES}

if "port_headings" not in st.session_state:
    st.session_state["port_headings"] = {
        "Long Beach Cruise Terminal": 135.0, "Mazatlan Pier 4/5": 315.0,
        "Mazatlan Pier 2/3": 135.0, "La Paz": 180.0, "Ensenada Pier #2": 220.0,
        "Puerto Vallarta Pier #1": 0.0, "Puerto Vallarta Pier #3": 0.0,
    }

# -----------------------------------------------------------------------------
# Calendar — persistent monthly source of truth
# -----------------------------------------------------------------------------
st.sidebar.title("🚢 Carnival Panorama")
st.sidebar.caption(f"LOA: {DEFAULT_SHIP['LOA']} m | Beam: {DEFAULT_SHIP['Beam']} m | Draft: {DEFAULT_SHIP['Draft']} m")
st.sidebar.divider()

def load_and_parse_itinerary(uploaded_file):
    df = pd.read_excel(uploaded_file)
    required = ["ETA", "ETD", "Date", "Location", "Port Code", "Confirmed Berthing", "Call Type"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing itinerary columns: {', '.join(missing)}")
    df_clean = df.dropna(subset=["ETA", "ETD", "Date"]).copy()
    df_clean["Date_Str"] = pd.to_datetime(df_clean["Date"]).dt.strftime("%Y-%m-%d")
    df_clean["ETA_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETA"].astype(str), errors="coerce")
    df_clean["ETD_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETD"].astype(str), errors="coerce")
    df_clean.loc[df_clean["ETD_dt"] < df_clean["ETA_dt"], "ETD_dt"] += pd.Timedelta(days=1)
    return pd.DataFrame({"Port": df_clean["Location"], "Port_Code": df_clean["Port Code"], "ETA": df_clean["ETA_dt"], "ETD": df_clean["ETD_dt"], "Berthing_Type": df_clean["Confirmed Berthing"], "Call_Type": df_clean["Call Type"]})

calendar_info = calendar_state()
st.session_state["port_schedule"] = calendar_info["schedule"] if not calendar_info["completed"] else pd.DataFrame()

if calendar_info["completed"] and not st.session_state.get("calendar_expiry_popup_shown", False):
    @st.dialog("📅 Calendario mensile completato")
    def show_calendar_expired_dialog():
        month = calendar_info.get("calendar_month") or "precedente"
        st.warning(f"Il calendario {month} è stato completato.")
        st.write("Caricare ora il calendario del mese successivo per riattivare l'automazione dei port call.")
        st.info("Il calendario precedente rimane conservato nello storage fino alla sostituzione.")
        if st.button("OK — Caricherò il nuovo calendario", use_container_width=True):
            st.session_state["calendar_expiry_popup_shown"] = True
            st.rerun()
    show_calendar_expired_dialog()

st.sidebar.header("📅 Port Call Schedule")
if calendar_info["calendar_month"] and not calendar_info["completed"]:
    st.sidebar.success(f"📅 Calendario attivo: {calendar_info['calendar_month']}")

schedule_file = st.sidebar.file_uploader("Carica Calendario Scali (.xlsx)", type=["xlsx", "xls"], key="schedule_uploader")
if schedule_file is not None:
    try:
        parsed_df = load_and_parse_itinerary(schedule_file)
        month = persist_calendar(parsed_df, getattr(schedule_file, "name", None))
        st.session_state["port_schedule"] = parsed_df
        st.session_state["calendar_expiry_popup_shown"] = True
        st.sidebar.success(f"✅ Calendario {month} caricato e salvato.")
    except Exception as exc:
        st.sidebar.error(f"Errore lettura Excel: {exc}")

if not st.session_state["port_schedule"].empty:
    st.sidebar.caption(f"💾 Scali salvati: {len(st.session_state['port_schedule'])}")
    if st.sidebar.button("🗑️ Rimuovi Calendario Salvato"):
        clear_calendar_storage()
        st.session_state["port_schedule"] = pd.DataFrame()
        st.rerun()

port_runtime = reconcile_schedule(st.session_state["port_schedule"])
st.session_state["mooring_runtime"] = port_runtime
runtime_status = port_runtime.get("status")
runtime_port = port_runtime.get("port")
runtime_configured_port = port_runtime.get("configured_port") or runtime_port
runtime_setup = port_runtime.get("setup")

if runtime_status == "IN_TRANSIT":
    st.sidebar.caption("⚓ Nessun port call attivo — nave in navigazione.")
elif runtime_status == "PORT_CALL_ACTIVE_SETUP_MISSING":
    st.sidebar.warning(f"📍 Port Call Attivo: {runtime_port}\n\n⚠️ Mooring Setup non disponibile/configurato.")
elif runtime_port:
    st.sidebar.info(f"📍 Port Call Attivo: {runtime_port}\n\n⚓ Mooring Setup: {runtime_setup or 'N/A'}")

st.sidebar.divider()
st.sidebar.header("🌐 Condizioni Meteo-Marine")
meteo_mode = st.sidebar.radio("Modalità Meteo:", ["Manuale", "Live API (Windy / Open-Meteo)"], index=0)
available_ports = list(st.session_state["ports_bollards"].keys())
default_port = runtime_configured_port if runtime_configured_port in available_ports else available_ports[0]
selected_port = st.sidebar.selectbox("📌 Porto di Riferimento", available_ports, index=available_ports.index(default_port))
current_berth_heading = float(st.session_state["port_headings"].get(selected_port, 0.0))
v_wind = float(st.sidebar.slider("Vento (knots)", 0, 80, 30, key="v_wind_slider"))
dir_wind = float(st.sidebar.slider("Direzione Vento Relativa (°)", 0, 360, 45, key="dir_wind_slider"))
v_curr = float(st.sidebar.slider("Corrente (knots)", 0.0, 4.0, 0.5, key="v_curr_slider"))
dir_curr = float(st.sidebar.slider("Direzione Corrente (deg)", 0, 360, 0, key="dir_curr_slider"))
st.session_state.update({"v_wind": v_wind, "dir_wind": dir_wind, "v_curr": v_curr, "dir_curr": dir_curr})
offset_fugro_m = float(st.sidebar.number_input("Offset from FUGRO position (m)", value=float(st.session_state.get("offset_fugro_m", 0.0)), step=0.5))
st.session_state["offset_fugro_m"] = offset_fugro_m

st.title("⚓ OpenMooring MEG4 Pro — Carnival Panorama")
(tab_auto_engine, tab_certs, tab_stations, tab_3d_editor, tab_sim, tab_polar, tab_maint) = st.tabs([
    "⚡ Automazione Ormeggio", "📜 1. Certificati Cavi", "🏗️ 2. Pianetti Mooring Stations",
    "🗺️ 3. Layout Banchina & Bitte", "📊 4. Simulazione Tensioni", "🌀 5. Inviluppo Polare", "📈 6. Storico & Usura Cavi",
])

with tab_auto_engine:
    render_tab_mooring_engine()
with tab_certs:
    render_tab_certificate()
with tab_stations:
    render_tab_plans()
with tab_3d_editor:
    render_tab_berth(selected_port, DEFAULT_SHIP)

active_bollards_df = st.session_state["ports_bollards"].get(selected_port, pd.DataFrame())
try:
    geom_df = calculate_line_geometry(st.session_state["lines_inventory"], active_bollards_df, loa=DEFAULT_SHIP["LOA"], offset_fugro=offset_fugro_m)
except Exception as exc:
    geom_df = pd.DataFrame()
    st.session_state["geometry_error"] = str(exc)
st.session_state["geom_df"] = geom_df

with tab_sim:
    if geom_df.empty:
        st.warning("⚠️ Geometria non disponibile per il porto selezionato.")
    else:
        forces = calculate_environmental_forces(v_wind, dir_wind, v_curr, dir_curr, DEFAULT_SHIP["AFW"], DEFAULT_SHIP["ALW"], DEFAULT_SHIP["ALC"], DEFAULT_SHIP["LOA"])
        results_df = solve_line_tensions_3d(geom_df, forces)
        st.subheader(f"Analisi Tensione Cavi: {selected_port}")
        m1, m2, m3 = st.columns(3)
        m1.metric("Fx", f"{forces['Fx_total_t']:.2f} t")
        m2.metric("Fy", f"{forces['Fy_total_t']:.2f} t")
        m3.metric("Mz", f"{forces['Mz_total_tm']:.2f} t·m")
        cols = [c for c in ["line_id", "line_name", "cert_id", "bollard_id", "length_m", "azimuth_deg", "incline_deg", "Tension_tons", "Util_Percent"] if c in results_df.columns]
        st.dataframe(results_df[cols], use_container_width=True)
        if st.button("💾 Registra Sessione d'Ormeggio nel DB"):
            log_mooring_session(results_df, selected_port)
            st.success("Sessione salvata nello storico usura!")
with tab_polar:
    render_tab_polar(v_wind=v_wind, dir_wind=dir_wind)
with tab_maint:
    render_tab_history()
