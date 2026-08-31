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

# Assicura che la directory radice sia nel PATH di sistema
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import dei moduli configurazione e database
from config.constants import (
    DB_FILE_PATH,
    DEFAULT_BOLLARDS,
    DEFAULT_SHIP,
    PORT_COORDINATES,
)

# Import DIRETTO dai singoli file della cartella core
from core.hydrodynamic_forces import calculate_environmental_forces
from core.line_mechanics import (
    calculate_line_geometry,
    solve_line_tensions_3d,
)

from database.db_manager import (
    init_db,
    log_mooring_session,
    load_port_bollards_from_db,
    save_certificate_to_db,
    load_certificates_from_db,
    save_lines_inventory_to_db,
    load_lines_inventory_from_db,
)
# Import gestione PDF con fallback di sicurezza
try:
    from utils.pdf_parser import extract_text_from_pdf, parse_certificate_text
except ImportError as e:
    def extract_text_from_pdf(*args, **kwargs):
        return ""
    def parse_certificate_text(*args, **kwargs):
        return {}
    st.error(f"⚠️ Errore caricamento modulo PDF (`utils.pdf_parser`): {e}")

# Import delle viste (Tabs)
from views.tab_berth import render_tab_berth
from views.tab_certificate import render_tab_certificate
from views.tab_history import render_tab_history
from views.tab_plans import render_tab_plans
from views.tab_polar import render_tab_polar
from views.tab_mooring_engine import render_tab_mooring_engine

# Configurazione della pagina Streamlit
st.set_page_config(
    page_title="OpenMooring MEG4 Pro — Carnival Panorama",
    layout="wide",
)

# Percorso per il salvataggio persistente del calendario su disco
CALENDAR_STORAGE_PATH = os.path.join(os.path.dirname(DB_FILE_PATH), "saved_schedule.parquet")

# =============================================================================
# 1. INIZIALIZZAZIONE DATABASE & CARICAMENTO PERSISTENTE
# =============================================================================
init_db()

# Inizializzazione variabili globali nave nello state per Tab Polare
st.session_state["afw"] = DEFAULT_SHIP.get("AFW", 950.0)
st.session_state["alw"] = DEFAULT_SHIP.get("ALW", 3200.0)
st.session_state["alc"] = DEFAULT_SHIP.get("ALC", 1800.0)
st.session_state["loa"] = DEFAULT_SHIP.get("LOA", 323.44)

# 1. CARICAMENTO PERSISTENTE CERTIFICATI
if "certificates_db" not in st.session_state:
    db_certs = load_certificates_from_db()
    if not db_certs.empty:
        st.session_state.certificates_db = db_certs
    else:
        default_certs = [
            {
                "cert_id": "CERT-HMPE-2025-01",
                "manufacturer": "Samson Rope",
                "material": "HMPE",
                "diameter_mm": 64.0,
                "mbl_tons": 105.0,
                "standard": "MEG4 / DNV",
                "issue_date": "2025-01-15",
            },
            {
                "cert_id": "CERT-HMPE-2025-02",
                "manufacturer": "Katradis",
                "material": "HMPE",
                "diameter_mm": 64.0,
                "mbl_tons": 105.0,
                "standard": "MEG4 / LRS",
                "issue_date": "2025-02-10",
            },
        ]
        for c in default_certs:
            save_certificate_to_db(c)
        st.session_state.certificates_db = load_certificates_from_db()

# 2. CARICAMENTO PERSISTENTE INVENTARIO CAVI
if "lines_inventory" not in st.session_state:
    db_lines = load_lines_inventory_from_db()
    if not db_lines.empty:
        st.session_state.lines_inventory = db_lines
    else:
        default_lines = pd.DataFrame([
            {
                "line_id": "1",
                "line_name": "Head Line 1",
                "line_type": "Head",
                "station_id": "Prua (Forward Station)",
                "winch_id": "W1",
                "cert_id": "CERT-HMPE-2025-01",
                "chock_x_m": 155.0,
                "chock_y_m": 2.0,
                "chock_z_m": 12.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 11.0,
                "tail_diameter_mm": 72,
                "tail_E_modulus_GPa": 6,
                "tail_mbl_tons": 100.0,
                "bollard_id": "B1",
            },
            {
                "line_id": "2",
                "line_name": "Head Line 2",
                "line_type": "Head",
                "station_id": "Prua (Forward Station)",
                "winch_id": "W2",
                "cert_id": "CERT-HMPE-2025-01",
                "chock_x_m": 155.0,
                "chock_y_m": -2.0,
                "chock_z_m": 12.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 11.0,
                "tail_diameter_mm": 72,
                "tail_E_modulus_GPa": 6,
                "tail_mbl_tons": 100.0,
                "bollard_id": "B1",
            },
            {
                "line_id": "3",
                "line_name": "Fwd Breast 1",
                "line_type": "Fwd Breast",
                "station_id": "Prua (Forward Station)",
                "winch_id": "W3",
                "cert_id": "CERT-HMPE-2025-02",
                "chock_x_m": 140.0,
                "chock_y_m": 18.0,
                "chock_z_m": 10.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 11.0,
                "tail_diameter_mm": 72,
                "tail_E_modulus_GPa": 6,
                "tail_mbl_tons": 100.0,
                "bollard_id": "B2",
            },
            {
                "line_id": "4",
                "line_name": "Fwd Spring 1",
                "line_type": "Fwd Spring",
                "station_id": "Prua (Forward Station)",
                "winch_id": "W4",
                "cert_id": "CERT-HMPE-2025-02",
                "chock_x_m": 110.0,
                "chock_y_m": 18.0,
                "chock_z_m": 8.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 0.0,
                "tail_diameter_mm": 0,
                "tail_E_modulus_GPa": 0,
                "tail_mbl_tons": 0,
                "bollard_id": "B3",
            },
            {
                "line_id": "5",
                "line_name": "Aft Spring 1",
                "line_type": "Aft Spring",
                "station_id": "Poppa (Aft Station)",
                "winch_id": "W5",
                "cert_id": "CERT-HMPE-2025-01",
                "chock_x_m": -110.0,
                "chock_y_m": 18.0,
                "chock_z_m": 8.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 0.0,
                "tail_diameter_mm": 0,
                "tail_E_modulus_GPa": 0,
                "tail_mbl_tons": 0,
                "bollard_id": "B4",
            },
            {
                "line_id": "6",
                "line_name": "Aft Breast 1",
                "line_type": "Aft Breast",
                "station_id": "Poppa (Aft Station)",
                "winch_id": "W6",
                "cert_id": "CERT-HMPE-2025-02",
                "chock_x_m": -140.0,
                "chock_y_m": 18.0,
                "chock_z_m": 10.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 11.0,
                "tail_diameter_mm": 72,
                "tail_E_modulus_GPa": 6,
                "tail_mbl_tons": 100.0,
                "bollard_id": "B5",
            },
            {
                "line_id": "7",
                "line_name": "Stern Line 1",
                "line_type": "Stern",
                "station_id": "Poppa (Aft Station)",
                "winch_id": "W7",
                "cert_id": "CERT-HMPE-2025-02",
                "chock_x_m": -155.0,
                "chock_y_m": 0.0,
                "chock_z_m": 12.0,
                "material": "HMPE",
                "diameter_mm": 64,
                "E_modulus_GPa": 120,
                "mbl_tons": 105.0,
                "tail_length_m": 11.0,
                "tail_diameter_mm": 72,
                "tail_E_modulus_GPa": 6,
                "tail_mbl_tons": 100.0,
                "bollard_id": "B5",
            },
        ])
        save_lines_inventory_to_db(default_lines)
        st.session_state.lines_inventory = load_lines_inventory_from_db()

# 3. CARICAMENTO PERSISTENTE BANCHINE E BITTE
if "ports_bollards" not in st.session_state:
    st.session_state.ports_bollards = {}
    ports_list = [
        "Long Beach Cruise Terminal",
        "Mazatlan Pier 4/5",
        "Mazatlan Pier 2/3",
        "La Paz",
        "Ensenada Pier #2",
        "Puerto Vallarta Pier #1",
        "Puerto Vallarta Pier #3",
    ]
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

# =============================================================================
# 2. BARRA LATERALE METEO, CALENDARIO SCALI & POSIZIONAMENTO NAVE
# =============================================================================
st.sidebar.title("🚢 Carnival Panorama")
st.sidebar.caption(
    f"LOA: {DEFAULT_SHIP['LOA']}m | Beam: {DEFAULT_SHIP['Beam']}m | Draft:"
    f" {DEFAULT_SHIP['Draft']}m"
)
st.sidebar.divider()

# FUNZIONE PARSER DEDICATA PER EXCEL CALENDARIO
def load_and_parse_itinerary(uploaded_file):
    df = pd.read_excel(uploaded_file)
    df_clean = df.dropna(subset=["ETA", "ETD", "Date"]).copy()
    df_clean["Date_Str"] = pd.to_datetime(df_clean["Date"]).dt.strftime("%Y-%m-%d")
    df_clean["ETA_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETA"].astype(str), errors="coerce")
    df_clean["ETD_dt"] = pd.to_datetime(df_clean["Date_Str"] + " " + df_clean["ETD"].astype(str), errors="coerce")
    df_clean.loc[df_clean["ETD_dt"] < df_clean["ETA_dt"], "ETD_dt"] += pd.Timedelta(days=1)
    
    parsed_df = pd.DataFrame({
        "Port": df_clean["Location"],
        "Port_Code": df_clean["Port Code"],
        "ETA": df_clean["ETA_dt"],
        "ETD": df_clean["ETD_dt"],
        "Berthing_Type": df_clean["Confirmed Berthing"],
        "Call_Type": df_clean["Call Type"]
    })
    return parsed_df

# INIZIALIZZAZIONE AUTOMATICA DA DISCO (SE PRESENTI DATI SALVATI)
if "port_schedule" not in st.session_state:
    if os.path.exists(CALENDAR_STORAGE_PATH):
        try:
            st.session_state["port_schedule"] = pd.read_parquet(CALENDAR_STORAGE_PATH)
        except Exception:
            st.session_state["port_schedule"] = pd.DataFrame()

# UPLOADER E PERSISTENZA CALENDARIO NELLA SIDEBAR
st.sidebar.header("📅 Port Call Schedule")
schedule_file = st.sidebar.file_uploader("Carica Calendario Scali (.xlsx)", type=["xlsx", "xls"], key="schedule_uploader")

if schedule_file is not None:
    try:
        parsed_df = load_and_parse_itinerary(schedule_file)
        st.session_state["port_schedule"] = parsed_df
        # Salvataggio fisico su disco per persistenza tra riavvii
        os.makedirs(os.path.dirname(CALENDAR_STORAGE_PATH), exist_ok=True)
        parsed_df.to_parquet(CALENDAR_STORAGE_PATH)
        st.sidebar.success("✅ Calendario caricato e salvato in memoria permanente!")
    except Exception as e:
        st.sidebar.error(f"Errore lettura Excel: {e}")

# Stato e pulizia del calendario in memoria
if "port_schedule" in st.session_state and not st.session_state["port_schedule"].empty:
    st.sidebar.caption(f"💾 **Scali salvati in memoria:** {len(st.session_state['port_schedule'])}")
    if st.sidebar.button("🗑️ Rimuovi Calendario Salvato"):
        if os.path.exists(CALENDAR_STORAGE_PATH):
            os.remove(CALENDAR_STORAGE_PATH)
        st.session_state["port_schedule"] = pd.DataFrame()
        st.rerun()

# Rilevamento automatico stato porto corrente
if "port_schedule" in st.session_state and not st.session_state["port_schedule"].empty:
    now_dt = datetime.now()
    sched = st.session_state["port_schedule"]
    active_port_df = sched[(sched["ETA"] <= now_dt) & (sched["ETD"] >= now_dt)]
    
    if not active_port_df.empty:
        curr_row = active_port_df.iloc[0]
        st.sidebar.info(
            f"📍 **Porto Attuale:** {curr_row['Port']}\n\n"
            f"⏱️ **ETA:** {curr_row['ETA'].strftime('%d/%m %H:%M')}\n\n"
            f"⏱️ **ETD:** {curr_row['ETD'].strftime('%d/%m %H:%M')}"
        )
    else:
        st.sidebar.caption("⚓ Nave in navigazione o nessun ormeggio attivo.")

st.sidebar.divider()

st.sidebar.header("🌐 Condizioni Meteo-Marine")
meteo_mode = st.sidebar.radio(
    "Modalità Meteo:",
    ["Manuale", "Live API (Windy / Open-Meteo)"],
    index=0,
)

selected_port = st.sidebar.selectbox(
    "📌 Porto di Riferimento", list(st.session_state.ports_bollards.keys())
)

current_berth_heading = st.session_state.port_headings.get(selected_port, 0.0)


def fetch_live_weather(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        res = requests.get(url, timeout=5).json()
        if "current_weather" in res:
            cw = res["current_weather"]
            wind_knots = cw["windspeed"] * 0.539957
            wind_deg = cw["winddirection"]
            return True, round(wind_knots, 1), round(wind_deg, 0)
    except Exception:
        pass
    return False, 0.0, 0.0


if meteo_mode == "Live API (Windy / Open-Meteo)":
    coords = PORT_COORDINATES.get(
        selected_port, {"lat": 33.7513, "lon": -118.1888}
    )
    success, live_w_speed, live_w_dir_true = fetch_live_weather(
        coords["lat"], coords["lon"]
    )

    if success:
        relative_wind_dir = (live_w_dir_true - current_berth_heading) % 360
        st.sidebar.success(
            f"Meteo Live: {live_w_speed} kts @ {live_w_dir_true}° True"
        )
        st.sidebar.info(
            f"🧭 Orientamento Banchina: {current_berth_heading:.0f}° True\n\n"
            f"💨 Vento Relativo Banchina: **{relative_wind_dir:.0f}°**"
        )
        v_wind = live_w_speed
        dir_wind = relative_wind_dir
    else:
        st.sidebar.error("Impossibile contattare il server meteo. Uso manuale.")
        v_wind = float(
            st.sidebar.slider("Vento (knots)", 0, 80, 30, key="v_wind_slider")
        )
        dir_wind = float(
            st.sidebar.slider(
                "Direzione Vento Relativa (°)",
                0,
                360,
                45,
                key="dir_wind_slider",
            )
        )
else:
    v_wind = float(
        st.sidebar.slider("Vento (knots)", 0, 80, 30, key="v_wind_slider")
    )
    dir_wind = float(
        st.sidebar.slider(
            "Direzione Vento Relativa (°)", 0, 360, 45, key="dir_wind_slider"
        )
    )

st.session_state["v_wind"] = v_wind
st.session_state["dir_wind"] = dir_wind

v_curr = st.sidebar.slider("Corrente (knots)", 0.0, 4.0, 0.5)
dir_curr = st.sidebar.slider("Direzione Corrente (deg)", 0, 360, 0)

# INPUT OFFSET LONGITUDINALE FUGRO
st.sidebar.divider()
st.sidebar.header("📐 Posizionamento Nave")
offset_fugro_m = st.sidebar.number_input(
    "Offset from FUGRO position (m)",
    value=0.0,
    step=0.5,
    help=(
        "Valore positivo: nave spostata verso Prua (+X). Valore negativo: verso"
        " Poppa (-X)."
    ),
)
st.session_state["offset_fugro_m"] = offset_fugro_m

# =============================================================================
# 3. INTERFACCIA PRINCIPALE E TABS
# =============================================================================
st.title("⚓ OpenMooring MEG4 Pro — Carnival Panorama")

(
    tab_auto_engine,
    tab_certs,
    tab_stations,
    tab_3d_editor,
    tab_sim,
    tab_polar,
    tab_maint,
) = st.tabs([
    "⚡ Automazione Ormeggio",
    "📜 1. Certificati Cavi (PDF Drag & Drop)",
    "🏗️ 2. Pianetti Mooring Stations",
    "🗺️ 3. Layout Banchina & Bitte",
    "📊 4. Simulazione Tensioni",
    "🌀 5. Inviluppo Polare",
    "📈 6. Storico & Usura Cavi",
])

# -----------------------------------------------------------------------------
# TAB AUTOMAZIONE ORMEGGIO (30 MINUTI & TRIGGER VENTO +-6 KTS)
# -----------------------------------------------------------------------------
with tab_auto_engine:
    render_tab_mooring_engine()

# -----------------------------------------------------------------------------
# TAB 1: CERTIFICATI CAVI (PERSISTENTE)
# -----------------------------------------------------------------------------
with tab_certs:
    render_tab_certificate()

# -----------------------------------------------------------------------------
# TAB 2: MOORING STATIONS & PIANETTI
# -----------------------------------------------------------------------------
with tab_stations:
    render_tab_plans()

# -----------------------------------------------------------------------------
# TAB 3: LAYOUT BANCHINA & BITTE (TELEMETRO)
# -----------------------------------------------------------------------------
with tab_3d_editor:
    render_tab_berth(selected_port, DEFAULT_SHIP)

active_bollards_df = st.session_state.ports_bollards[selected_port]
geom_df = calculate_line_geometry(
    st.session_state.lines_inventory,
    active_bollards_df,
    loa=DEFAULT_SHIP["LOA"],
    offset_fugro=offset_fugro_m,
)
st.session_state["geom_df"] = geom_df

# -----------------------------------------------------------------------------
# TAB 4: SIMULAZIONE TENSIONI
# -----------------------------------------------------------------------------
with tab_sim:
    if geom_df.empty:
        st.error(
            "⚠️ Nessuna corrispondenza trovata tra le bitte dei cavi e della"
            " banchina."
        )
    else:
        forces = calculate_environmental_forces(
            v_wind,
            dir_wind,
            v_curr,
            dir_curr,
            DEFAULT_SHIP["AFW"],
            DEFAULT_SHIP["ALW"],
            DEFAULT_SHIP["ALC"],
            DEFAULT_SHIP["LOA"],
        )
        results_df = solve_line_tensions_3d(geom_df, forces)

        st.subheader(
            f"Analisi Tensione Cavi: **{selected_port}** (Meteo: {v_wind} kts @"
            f" {dir_wind}° | Offset: {offset_fugro_m:+.2f}m)"
        )
        m1, m2, m3 = st.columns(3)
        m1.metric("Forza Longitudinale (Fx)", f"{forces['Fx_total_t']:.2f} t")
        m2.metric("Forza Trasversale (Fy)", f"{forces['Fy_total_t']:.2f} t")
        m3.metric("Momento Imbardata (Mz)", f"{forces['Mz_total_tm']:.2f} t·m")

        st.dataframe(
            results_df[[
                "line_id",
                "line_name",
                "cert_id",
                "bollard_id",
                "length_m",
                "azimuth_deg",
                "incline_deg",
                "Tension_tons",
                "Util_Percent",
            ]],
            use_container_width=True,
        )

        if st.button("💾 Registra Sessione d'Ormeggio nel DB"):
            log_mooring_session(results_df, selected_port)
            st.success("Sessione salvata nello storico usura!")

# -----------------------------------------------------------------------------
# TAB 5: INVILUPPO POLARE
# -----------------------------------------------------------------------------
with tab_polar:
    render_tab_polar(v_wind=v_wind, dir_wind=dir_wind)

# -----------------------------------------------------------------------------
# TAB 6: STORICO & USURA CAVI
# -----------------------------------------------------------------------------
with tab_maint:
    render_tab_history()
