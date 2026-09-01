"""
app.py
Punto di ingresso principale della suite OpenMooring MEG4 Pro.
Configurazione blindata con sincronizzazione, caricamento Calendario nella Sidebar e Tab Automazione Ormeggio.
"""

from datetime import datetime
import os
import sqlite3
import sys
import pandas as pd
import requests
import streamlit as st

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.constants import (
    DB_FILE_PATH,
    DEFAULT_BOLLARDS,
    DEFAULT_SHIP,
    PORT_COORDINATES,
)
from core.hydrodynamic_forces import calculate_environmental_forces
from core.line_mechanics import calculate_line_geometry, solve_line_tensions_3d
from core.schedule_runtime import reconcile_schedule
from database.db_manager import (
    init_db,
    log_mooring_session,
    load_port_bollards_from_db,
    save_certificate_to_db,
    load_certificates_from_db,
    save_lines_inventory_to_db,
    load_lines_inventory_from_db,
)

try:
    from utils.pdf_parser import extract_text_from_pdf, parse_certificate_text, parse_line_certificate
except Exception as e:
    st.error(f"⚠️ Errore durante l'importazione di `utils.pdf_parser`: {e}")

from views.tab_berth import render_tab_berth
from views.tab_certificate import render_tab_certificate
from views.tab_history import render_tab_history
from views.tab_plans import render_tab_plans
from views.tab_polar import render_tab_polar
from views.tab_mooring_engine import render_tab_mooring_engine

st.set_page_config(page_title="OpenMooring MEG4 Pro — Carnival Panorama", layout="wide")
CALENDAR_STORAGE_PATH = os.path.join(os.path.dirname(DB_FILE_PATH), "saved_schedule.parquet")

init_db()
st.session_state["afw"] = DEFAULT_SHIP.get("AFW", 950.0)
st.session_state["alw"] = DEFAULT_SHIP.get("ALW", 3200.0)
st.session_state["alc"] = DEFAULT_SHIP.get("ALC", 1800.0)
st.session_state["loa"] = DEFAULT_SHIP.get("LOA", 323.44)

if "certificates_db" not in st.session_state:
    db_certs = load_certificates_from_db()
    if not db_certs.empty:
        st.session_state.certificates_db = db_certs
    else:
        default_certs = [
            {"cert_id": "CERT-HMPE-2025-01", "manufacturer": "Samson Rope", "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "standard": "MEG4 / DNV", "issue_date": "2025-01-15"},
            {"cert_id": "CERT-HMPE-2025-02", "manufacturer": "Katradis", "material": "HMPE", "diameter_mm": 64.0, "mbl_tons": 105.0, "standard": "MEG4 / LRS", "issue_date": "2025-02-10"},
        ]
        for c in default_certs:
            save_certificate_to_db(c)
        st.session_state.certificates_db = load_certificates_from_db()

if "lines_inventory" not in st.session_state:
    db_lines = load_lines_inventory_from_db()
    if not db_lines.empty:
        st.session_state.lines_inventory = db_lines
    else:
        default_lines = pd.DataFrame([
            {"line_id": "1", "line_name": "Head Line 1", "line_type": "Head", "station_id": "Prua (Forward Station)", "winch_id": "W1", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": 155.0, "chock_y_m": 2.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72, "tail_E_modulus_GPa": 6, "tail_mbl_tons": 100.0, "bollard_id": "B1"},
            {"line_id": "2", "line_name": "Head Line 2", "line_type": "Head", "station_id": "Prua (Forward Station)", "winch_id": "W2", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": 155.0, "chock_y_m": -2.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72, "tail_E_modulus_GPa": 6, "tail_mbl_tons": 100.0, "bollard_id": "B1"},
            {"line_id": "3", "line_name": "Fwd Breast 1", "line_type": "Fwd Breast", "station_id": "Prua (Forward Station)", "winch_id": "W3", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": 140.0, "chock_y_m": 18.0, "chock_z_m": 10.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72, "tail_E_modulus_GPa": 6, "tail_mbl_tons": 100.0, "bollard_id": "B2"},
            {"line_id": "4", "line_name": "Fwd Spring 1", "line_type": "Fwd Spring", "station_id": "Prua (Forward Station)", "winch_id": "W4", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": 110.0, "chock_y_m": 18.0, "chock_z_m": 8.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 0.0, "tail_diameter_mm": 0, "tail_E_modulus_GPa": 0, "tail_mbl_tons": 0, "bollard_id": "B3"},
            {"line_id": "5", "line_name": "Aft Spring 1", "line_type": "Aft Spring", "station_id": "Poppa (Aft Station)", "winch_id": "W5", "cert_id": "CERT-HMPE-2025-01", "chock_x_m": -110.0, "chock_y_m": 18.0, "chock_z_m": 8.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 0.0, "tail_diameter_mm": 0, "tail_E_modulus_GPa": 0, "tail_mbl_tons": 0, "bollard_id": "B4"},
            {"line_id": "6", "line_name": "Aft Breast 1", "line_type": "Aft Breast", "station_id": "Poppa (Aft Station)", "winch_id": "W6", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": -140.0, "chock_y_m": 18.0, "chock_z_m": 10.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72, "tail_E_modulus_GPa": 6, "tail_mbl_tons": 100.0, "bollard_id": "B5"},
            {"line_id": "7", "line_name": "Stern Line 1", "line_type": "Stern", "station_id": "Poppa (Aft Station)", "winch_id": "W7", "cert_id": "CERT-HMPE-2025-02", "chock_x_m": -155.0, "chock_y_m": 0.0, "chock_z_m": 12.0, "material": "HMPE", "diameter_mm": 64, "E_modulus_GPa": 120, "mbl_tons": 105.0, "tail_length_m": 11.0, "tail_diameter_mm": 72, "tail_E_modulus_GPa": 6, "tail_mbl_tons": 100.0, "bollard_id": "B5"},
        ])
        save_lines_inventory_to_db(default_lines)
        st.session_state.lines_inventory = load_lines_inventory_from_db()

if "ports_bollards" not in st.session_state:
    st.session_state.ports_bollards = {}
    ports_list = ["Long Beach Cruise Terminal", "Mazatlan Pier 4/5", "Mazatlan Pier 2/3", "La Paz", "Ensenada Pier #2", "Puerto Vallarta Pier #1", "Puerto Vallarta Pier #3"]
    for p in ports_list:
        st.session_state.ports_bollards[p] = load_port_bollards_from_db(p)

if "port_headings" not in st.session_state:
    st.session_state.port_headings = {
        "Long Beach Cruise Terminal": 135.0,
        "Mazatlan Pier 4/5": 315.0,
        "Mazatlan Pier 2/3": 135.0,
        "La Paz": 180.0,
        "Ensenada Pier #2": 220.0,
        "Puerto Vallarta Pier #1": 0.0,
        "Puerto Vallarta Pier #3": 0.0,
    }

st.sidebar.title("🚢 Carnival Panorama")
st.sidebar.caption(f"LOA: {DEFAULT_SHIP['LOA']}m | Beam: {DEFAULT_SHIP['Beam']}m | Draft: {DEFAULT_SHIP['Draft']}m")
st.sidebar.divider()

def load_and_parse_itinerary(uploaded_file):
    df = pd.read_excel(uploaded_file)
    df_clean = df.dropna(subset=["ETA", "ETD", "Date"]).copy()
    df_clean["Date_Str"] = pd.to_datetime(df_clean["Date"]).dt.strftime("%Y-%m-%d")
    df_clean["ETA_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETA"].astype(str), errors="coerce")
    df_clean["ETD_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETD"].astype(str), errors="coerce")
    df_clean.loc[df_clean["ETD_dt"] < df_clean["ETA_dt"], "ETD_dt"] += pd.Timedelta(days=1)
    return pd.DataFrame({
        "Port": df_clean["Location"],
        "Port_Code": df_clean["Port Code"],
        "ETA": df_clean["ETA_dt"],
        "ETD": df_clean["ETD_dt"],
        "Berthing_Type": df_clean["Confirmed Berthing"],
        "Call_Type": df_clean["Call Type"],
    })

if "port_schedule" not in st.session_state:
    if os.path.exists(CALENDAR_STORAGE_PATH):
        try:
            st.session_state["port_schedule"] = pd.read_parquet(CALENDAR_STORAGE_PATH)
        except Exception:
            st.session_state["port_schedule"] = pd.DataFrame()

st.sidebar.header("📅 Port Call Schedule")
schedule_file = st.sidebar.file_uploader("Carica Calendario Scali (.xlsx)", type=["xlsx", "xls"], key="schedule_uploader")
if schedule_file is not None:
    try:
        parsed_df = load_and_parse_itinerary(schedule_file)
        st.session_state["port_schedule"] = parsed_df
        os.makedirs(os.path.dirname(CALENDAR_STORAGE_PATH), exist_ok=True)
        parsed_df.to_parquet(CALENDAR_STORAGE_PATH)
        st.sidebar.success("✅ Calendario caricato e salvato in memoria permanente!")
    except Exception as e:
        st.sidebar.error(f"Errore lettura Excel: {e}")

if "port_schedule" in st.session_state and not st.session_state["port_schedule"].empty:
    st.sidebar.caption(f"💾 **Scali salvati in memoria:** {len(st.session_state['port_schedule'])}")
    if st.sidebar.button("🗑️ Rimuovi Calendario Salvato"):
        if os.path.exists(CALENDAR_STORAGE_PATH):
            os.remove(CALENDAR_STORAGE_PATH)
        st.session_state["port_schedule"] = pd.DataFrame()
        st.rerun()

# SINGLE SOURCE OF TRUTH: calendar -> port call -> setup availability.
port_runtime = {"status": "IN_TRANSIT", "port": None, "operator": False, "setup": None}
if "port_schedule" in st.session_state and not st.session_state["port_schedule"].empty:
    try:
        port_runtime = reconcile_schedule(st.session_state["port_schedule"])
        st.session_state["mooring_runtime"] = port_runtime
    except Exception as exc:
        st.session_state["mooring_runtime_error"] = str(exc)
        st.sidebar.warning(f"⚠️ Mooring runtime non disponibile: {exc}")

runtime_status = port_runtime.get("status")
runtime_port = port_runtime.get("port")
runtime_setup = port_runtime.get("setup")

if runtime_status == "IN_TRANSIT":
    st.sidebar.caption("⚓ Nessun port call attivo nel calendario — nave in navigazione.")
elif runtime_status == "PORT_CALL_ACTIVE_SETUP_MISSING":
    st.sidebar.warning(
        f"📍 **Port Call Attivo: {runtime_port}**\n\n"
        "⚠️ **Mooring Setup non disponibile per questo porto.**\n\n"
        "Il sistema NON considera la nave in navigazione. Inserire/configurare il Mooring Setup prima di eseguire il calcolo."
    )
    st.sidebar.caption(
        f"ETA: {pd.to_datetime(port_runtime['scheduled_start_utc']).strftime('%d/%m %H:%M UTC')} | "
        f"ETD: {pd.to_datetime(port_runtime['scheduled_end_utc']).strftime('%d/%m %H:%M UTC')}"
    )
elif runtime_port:
    st.sidebar.info(
        f"📍 **Port Call Attivo:** {runtime_port}\n\n"
        f"⚓ **Mooring Setup:** {runtime_setup or 'N/A'}"
    )

st.sidebar.divider()
st.sidebar.header("🌐 Condizioni Meteo-Marine")
meteo_mode = st.sidebar.radio("Modalità Meteo:", ["Manuale", "Live API (Windy / Open-Meteo)"])
