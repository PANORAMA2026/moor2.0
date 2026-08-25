"""
app.py
Punto di ingresso principale della suite OpenMooring MEG4 Pro.
Configurazione blindata in default con i dati da config/constants.py.
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
    DEFAULT_SHIP,
    OFFSET_PLATFORM_AFT_M,
    OFFSET_PLATFORM_FWD_M,
)

# Import DIRETTO dai singoli file della cartella core
from core.hydrodynamic_forces import calculate_environmental_forces
from core.line_mechanics import (
    calculate_line_geometry,
    calculate_wind_operability_envelope,
    solve_line_tensions_3d,
)

from database.db_manager import init_db, log_mooring_session
from utils.pdf_parser import extract_text_from_pdf, parse_certificate_text

# Import delle viste (Tabs)
from views.tab_berth import render_tab_berth
from views.tab_history import render_tab_history
from views.tab_plans import render_tab_plans

# Configurazione della pagina Streamlit
st.set_page_config(
    page_title="OpenMooring MEG4 Pro - Carnival Panorama",
    layout="wide",
)

# =============================================================================
# 1. INIZIALIZZAZIONE DATABASE & SESSION STATE
# =============================================================================
DB_PATH = "openmooring.db"

if "db_conn" not in st.session_state:
    st.session_state.db_conn = sqlite3.connect(
        DB_PATH, check_same_thread=False
    )
    st.session_state.db_conn.row_factory = sqlite3.Row

# Inizializzazione dati di default se non presenti in sessione
if "certificates_db" not in st.session_state:
    st.session_state.certificates_db = pd.DataFrame([
        {
            "cert_id": "CERT-HMPE-2025-01",
            "manufacturer": "Samson Rope",
            "material": "HMPE",
            "diameter_mm": 64,
            "mbl_tons": 105.0,
            "standard": "MEG4 / DNV",
            "issue_date": "2025-01-15",
        },
        {
            "cert_id": "CERT-HMPE-2025-02",
            "manufacturer": "Katradis",
            "material": "HMPE",
            "diameter_mm": 64,
            "mbl_tons": 105.0,
            "standard": "MEG4 / LRS",
            "issue_date": "2025-02-10",
        },
    ])

if "mooring_stations" not in st.session_state:
    st.session_state.mooring_stations = {
        "Prua (Forward Station)": pd.DataFrame([
            {
                "winch_id": "W1",
                "chock_id": "C1",
                "chock_x_m": 150.0,
                "chock_y_m": 2.0,
                "assigned_line_id": "1",
            },
            {
                "winch_id": "W2",
                "chock_id": "C2",
                "chock_x_m": 150.0,
                "chock_y_m": -2.0,
                "assigned_line_id": "2",
            },
            {
                "winch_id": "W3",
                "chock_id": "C3",
                "chock_x_m": 138.0,
                "chock_y_m": 18.0,
                "assigned_line_id": "3",
            },
            {
                "winch_id": "W4",
                "chock_id": "C4",
                "chock_x_m": 110.0,
                "chock_y_m": 18.0,
                "assigned_line_id": "4",
            },
        ]),
        "Poppa (Aft Station)": pd.DataFrame([
            {
                "winch_id": "W5",
                "chock_id": "C5",
                "chock_x_m": -110.0,
                "chock_y_m": 18.0,
                "assigned_line_id": "5",
            },
            {
                "winch_id": "W6",
                "chock_id": "C6",
                "chock_x_m": -138.0,
                "chock_y_m": 18.0,
                "assigned_line_id": "6",
            },
            {
                "winch_id": "W7",
                "chock_id": "C7",
                "chock_x_m": -150.0,
                "chock_y_m": 0.0,
                "assigned_line_id": "7",
            },
        ]),
    }

if "lines_inventory" not in st.session_state:
    st.session_state.lines_inventory = pd.DataFrame([
        {
            "line_id": "1",
            "line_name": "Head Line 1",
            "line_type": "Head",
            "station_id": "Prua (Forward Station)",
            "winch_id": "W1",
            "cert_id": "CERT-HMPE-2025-01",
            "chock_x_m": 150.0,
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
            "chock_x_m": 150.0,
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
            "chock_x_m": 138.0,
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
            "chock_x_m": -138.0,
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
            "chock_x_m": -150.0,
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

if "ports_bollards" not in st.session_state:
    st.session_state.ports_bollards = {
        "Long Beach Cruise Terminal": pd.DataFrame(DEFAULT_BOLLARDS),
        "Mazatlan Pier 4/5": pd.DataFrame(DEFAULT_BOLLARDS),
        "Mazatlan Pier 2/3": pd.DataFrame(DEFAULT_BOLLARDS),
        "La Paz": pd.DataFrame(DEFAULT_BOLLARDS),
        "Ensenada Pier #2": pd.DataFrame(DEFAULT_BOLLARDS),
        "Puerto Vallarta Pier #1": pd.DataFrame(DEFAULT_BOLLARDS),
        "Puerto Vallarta Pier #3": pd.DataFrame(DEFAULT_BOLLARDS),
    }

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

init_db(st.session_state.lines_inventory)

# =============================================================================
# 2. BARRA LATERALE METEO & DATI NAVE
# =============================================================================
st.sidebar.title("🚢 Carnival Panorama")
st.sidebar.caption(
    f"LOA: {DEFAULT_SHIP['LOA']}m | Beam: {DEFAULT_SHIP['Beam']}m | Draft: {DEFAULT_SHIP['Draft']}m"
)
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
        v_wind = st.sidebar.slider("Vento (knots)", 0, 80, 30)
        dir_wind = st.sidebar.slider("Direzione Vento Relativa (°)", 0, 360, 45)
else:
    v_wind = st.sidebar.slider("Vento (knots)", 0, 80, 30)
    dir_wind = st.sidebar.slider("Direzione Vento Relativa (°)", 0, 360, 45)

v_curr = st.sidebar.slider("Corrente (knots)", 0.0, 4.0, 0.5)
dir_curr = st.sidebar.slider("Direzione Corrente (deg)", 0, 360, 0)

# =============================================================================
# 3. INTERFACCIA PRINCIPALE E TABS
# =============================================================================
st.title("⚓ OpenMooring MEG4 Pro — Carnival Panorama")

(
    tab_certs,
    tab_stations,
    tab_3d_editor,
    tab_sim,
    tab_polar,
    tab_maint,
) = st.tabs([
    "📜 1. Certificati Cavi (PDF Drag & Drop)",
    "🏗️ 2. Pianetti Mooring Stations",
    "🗺️ 3. Layout Banchina & Bitte",
    "📊 4. Simulazione Tensioni",
    "🌀 5. Inviluppo Polare",
    "📈 6. Storico & Usura Cavi",
])

# -----------------------------------------------------------------------------
# TAB 1: CERTIFICATI CAVI
# -----------------------------------------------------------------------------
with tab_certs:
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
    st.info(
        "📁 **Drag & Drop Certificato:** Trascina direttamente il file PDF del"
        " certificato del cavo."
    )

    c_col1, c_col2 = st.columns([1, 1])
    with c_col1:
        uploaded_pdf = st.file_uploader(
            "Trascina qui il file PDF", type=["pdf"]
        )
        cert_text_to_parse = ""

        if uploaded_pdf is not None:
            st.success(f"File caricato: {uploaded_pdf.name}")
            cert_text_to_parse = extract_text_from_pdf(uploaded_pdf)

        manual_text = st.text_area(
            "Oppure incolla qui il testo del certificato", height=100
        )
        if manual_text:
            cert_text_to_parse = manual_text

        if st.button("🔍 Esegui Parsing Certificato"):
            if cert_text_to_parse:
                parsed = parse_certificate_text(cert_text_to_parse)
                st.success("Parsing completato!")
                st.json(parsed)

                new_cert_id = (
                    parsed["cert_id"]
                    or f"CERT-{len(st.session_state.certificates_db)+1}"
                )
                new_cert = {
                    "cert_id": new_cert_id,
                    "manufacturer": parsed["manufacturer"] or "Unknown",
                    "material": parsed["material"] or "HMPE",
                    "diameter_mm": parsed["diameter_mm"] or 64,
                    "mbl_tons": parsed["mbl_tons"] or 105.0,
                    "standard": parsed["standard"] or "MEG4",
                    "issue_date": datetime.now().strftime("%Y-%m-%d"),
                }
                st.session_state.certificates_db = pd.concat(
                    [
                        st.session_state.certificates_db,
                        pd.DataFrame([new_cert]),
                    ],
                    ignore_index=True,
                ).drop_duplicates(subset=["cert_id"], keep="last")
                st.rerun()

    with c_col2:
        st.subheader("📚 Database Certificati Registrati")
        st.dataframe(
            st.session_state.certificates_db,
            use_container_width=True,
            height=280,
        )

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
    st.session_state.lines_inventory, active_bollards_df
)

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
            f" {dir_wind}°)"
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
    st.subheader("Inviluppo Polare dei Limiti Operativi del Vento (0-360°)")
    if st.button("Esegui Simulazione Polare") and not geom_df.empty:
        with st.spinner("Calcolo dinamico in corso..."):
            angles, max_winds = calculate_wind_operability_envelope(
                geom_df,
                DEFAULT_SHIP["AFW"],
                DEFAULT_SHIP["ALW"],
                DEFAULT_SHIP["ALC"],
                DEFAULT_SHIP["LOA"],
                v_curr=v_curr,
                dir_curr=dir_curr,
            )
            st.success("Calcolo inviluppo completato!")

# -----------------------------------------------------------------------------
# TAB 6: STORICO & USURA CAVI
# -----------------------------------------------------------------------------
with tab_maint:
    render_tab_history()
