import sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

st.set_page_config(
    page_title="OpenMooring MEG4 Pro - Multi-Port", layout="wide"
)

# Costante di conversione (kN in tonnellate metriche)
KN_TO_TONS = 0.10197162129779

# =============================================================================
# 1. DATABASE & MANUTENZIONE PREDITTIVA (SQLite)
# =============================================================================
DB_NAME = "mooring_history.db"


def init_db(lines_df=None):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_history (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            mbl_tons REAL,
            max_design_hours REAL DEFAULT 2000.0,
            accumulated_hours REAL DEFAULT 0.0,
            high_load_hours REAL DEFAULT 0.0,
            fatigue_index REAL DEFAULT 0.0
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS mooring_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            port_name TEXT,
            line_id TEXT,
            tension_tons REAL,
            util_percent REAL,
            duration_hours REAL
        )
    """)

  if lines_df is not None:
    for _, row in lines_df.iterrows():
      cursor.execute(
          """
                INSERT OR IGNORE INTO line_history (line_id, line_name, mbl_tons)
                VALUES (?, ?, ?)
            """,
          (str(row["line_id"]), str(row["line_name"]), float(row["mbl_tons"])),
      )

  conn.commit()
  conn.close()


def log_mooring_session(results_df, port_name, duration_hours=6.0):
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  for _, row in results_df.iterrows():
    line_id = str(row["line_id"])
    tension = float(row["Tension_tons"])
    util = float(row["Util_Percent"])

    cursor.execute(
        """
            INSERT INTO mooring_logs (timestamp, port_name, line_id, tension_tons, util_percent, duration_hours)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        (now_str, port_name, line_id, tension, util, duration_hours),
    )

    fatigue_increment = ((util / 100.0) ** 3) * duration_hours
    high_load_inc = duration_hours if util > 35.0 else 0.0

    cursor.execute(
        """
            UPDATE line_history
            SET accumulated_hours = accumulated_hours + ?,
                high_load_hours = high_load_hours + ?,
                fatigue_index = fatigue_index + ?
            WHERE line_id = ?
        """,
        (duration_hours, high_load_inc, fatigue_increment, line_id),
    )

  conn.commit()
  conn.close()


def get_lines_health_status():
  conn = sqlite3.connect(DB_NAME)
  df = pd.read_sql_query("SELECT * FROM line_history", conn)
  conn.close()

  if df.empty:
    return df

  health_percent = []
  recommendations = []

  for _, row in df.iterrows():
    hours_used_pct = (
        row["accumulated_hours"] / row["max_design_hours"]
    ) * 100.0
    fatigue_pct = (row["fatigue_index"] / 300.0) * 100.0
    wear_pct = max(hours_used_pct, fatigue_pct)
    remaining_health = max(0.0, 100.0 - wear_pct)

    health_percent.append(remaining_health)

    if remaining_health <= 20.0:
      recommendations.append(
          "🚨 SOSTITUZIONE IMMINENTE: Cavo a fine vita utile!"
      )
    elif remaining_health <= 40.0:
      recommendations.append(
          "⚠️ ISPEZIONE: Valutare rotazione testa-coda (End-for-End)."
      )
    else:
      recommendations.append("✅ IDONEO: Condizioni operative regolari.")

  df["Health_Percent"] = health_percent
  df["Recommendation"] = recommendations
  return df


# =============================================================================
# 2. COORDINATE PORTO & METEO AUTOMATICO
# =============================================================================
PORT_COORDINATES = {
    "Long Beach Cruise Terminal": {"lat": 33.7513, "lon": -118.1888},
    "Mazatlan Pier 4/5": {"lat": 23.1978, "lon": -106.4211},
    "Mazatlan Pier 2/3": {"lat": 23.1950, "lon": -106.4200},
    "La Paz": {"lat": 24.1422, "lon": -110.3128},
    "Ensenada Pier #2": {"lat": 31.8578, "lon": -116.6258},
    "Puerto Vallarta Pier #1": {"lat": 20.6534, "lon": -105.2403},
    "Puerto Vallarta Pier #3": {"lat": 20.6560, "lon": -105.2415},
}


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


# =============================================================================
# 3. MOTORE FISICO & GEOMETRICO (RISULTATI IN TONNELLATE)
# =============================================================================
def calculate_environmental_forces(
    v_wind_knots,
    dir_wind_deg,
    v_curr_knots,
    dir_curr_deg,
    afw,
    alw,
    alc,
    loa,
):
  v_wind = float(v_wind_knots) * 0.514444
  v_curr = float(v_curr_knots) * 0.514444
  rho_air = 1.225
  rho_water = 1025.0

  rad_wind = np.radians(float(dir_wind_deg))
  rad_curr = np.radians(float(dir_curr_deg))

  cx_w = -np.cos(rad_wind)
  cy_w = np.sin(rad_wind)
  cmz_w = 0.15 * np.sin(2 * rad_wind)

  cx_c = -0.5 * np.cos(rad_curr)
  cy_c = np.sin(rad_curr)
  cmz_c = 0.1 * np.sin(2 * rad_curr)

  fx_w = (0.5 * rho_air * (v_wind**2) * float(afw) * cx_w / 1000.0) * KN_TO_TONS
  fy_w = (0.5 * rho_air * (v_wind**2) * float(alw) * cy_w / 1000.0) * KN_TO_TONS
  mz_w = (
      0.5 * rho_air * (v_wind**2) * float(alw) * float(loa) * cmz_w / 1000.0
  ) * KN_TO_TONS

  fx_c = (
      0.5 * rho_water * (v_curr**2) * float(afw) * 0.1 * cx_c / 1000.0
  ) * KN_TO_TONS
  fy_c = (
      0.5 * rho_water * (v_curr**2) * float(alc) * cy_c / 1000.0
  ) * KN_TO_TONS
  mz_c = (
      0.5 * rho_water * (v_curr**2) * float(alc) * float(loa) * cmz_c / 1000.0
  ) * KN_TO_TONS

  return {
      "Fx_total_t": fx_w + fx_c,
      "Fy_total_t": fy_w + fy_c,
      "Mz_total_tm": mz_w + mz_c,
  }


def calculate_line_geometry(lines_df, bollards_df):
  l_df = lines_df.copy()
  b_df = bollards_df.copy()

  l_df["bollard_id"] = l_df["bollard_id"].astype(str).str.strip()
  b_df["bollard_id"] = b_df["bollard_id"].astype(str).str.strip()

  merged = pd.merge(
      l_df, b_df, on="bollard_id", suffixes=("_chock", "_bollard")
  )

  if merged.empty:
    return merged

  x_col = "X_Coordinata_m" if "X_Coordinata_m" in merged.columns else "bollard_x_m"
  y_col = "Y_Coordinata_m" if "Y_Coordinata_m" in merged.columns else "bollard_y_m"
  z_col = "Z_Altezza_m" if "Z_Altezza_m" in merged.columns else "bollard_z_m"

  dx = merged[x_col].astype(float) - merged["chock_x_m"].astype(float)
  dy = merged[y_col].astype(float) - merged["chock_y_m"].astype(float)
  dz = merged[z_col].astype(float) - merged["chock_z_m"].astype(float)

  length_3d = np.sqrt(dx**2 + dy**2 + dz**2)
  length_2d = np.sqrt(dx**2 + dy**2)

  merged["length_m"] = length_3d
  merged["azimuth_deg"] = np.degrees(np.arctan2(dy, dx)) % 360
  merged["incline_deg"] = np.degrees(np.arctan2(dz, length_2d))
  merged["bollard_x_rendered"] = merged[x_col]
  merged["bollard_y_rendered"] = merged[y_col]
  merged["bollard_z_rendered"] = merged[z_col]

  return merged


def calculate_composite_stiffness(line):
  length_tail = float(line.get("tail_length_m", 0.0))
  length_main = max(0.1, float(line["length_m"]) - length_tail)
  area_main = np.pi * ((float(line["diameter_mm"]) / 1000.0) ** 2) / 4.0

  k_main = ((
      float(line["E_modulus_GPa"]) * 1e6 * area_main
  ) / length_main) * KN_TO_TONS

  if length_tail <= 0 or float(line.get("tail_diameter_mm", 0)) <= 0:
    return k_main, float(line["mbl_tons"])

  area_tail = (
      np.pi * ((float(line["tail_diameter_mm"]) / 1000.0) ** 2) / 4.0
  )
  k_tail = ((
      float(line["tail_E_modulus_GPa"]) * 1e6 * area_tail
  ) / length_tail) * KN_TO_TONS

  k_eq = (k_main * k_tail) / (k_main + k_tail)
  effective_mbl = min(
      float(line["mbl_tons"]),
      float(line.get("tail_mbl_tons", line["mbl_tons"])),
  )

  return k_eq, effective_mbl


def solve_line_tensions_3d(lines_geom_df, forces):
  if lines_geom_df.empty:
    return lines_geom_df

  K_global = np.zeros((3, 3))
  F_ext = np.array(
      [forces["Fx_total_t"], forces["Fy_total_t"], forces["Mz_total_tm"]]
  )
  line_data = []

  for _, line in lines_geom_df.iterrows():
    rad_az = np.radians(float(line["azimuth_deg"]))
    rad_inc = np.radians(float(line["incline_deg"]))

    dx = np.cos(rad_inc) * np.cos(rad_az)
    dy = np.cos(rad_inc) * np.sin(rad_az)

    k_eq, effective_mbl = calculate_composite_stiffness(line)

    rx, ry = float(line["chock_x_m"]), float(line["chock_y_m"])
    m_z = rx * dy - ry * dx

    b = np.array([dx, dy, m_z])
    K_global += k_eq * np.outer(b, b)

    line_data.append({"k": k_eq, "b": b, "mbl": effective_mbl})

  try:
    displacements = np.linalg.solve(K_global, F_ext)
  except np.linalg.LinAlgError:
    displacements = np.zeros(3)

  tensions, utilizations = [], []
  for item in line_data:
    t = max(0.0, item["k"] * np.dot(item["b"], displacements))
    tensions.append(t)
    utilizations.append((t / item["mbl"]) * 100.0)

  lines_geom_df["Tension_tons"] = tensions
  lines_geom_df["Util_Percent"] = utilizations
  return lines_geom_df


def calculate_wind_operability_envelope(
    lines_geom_df,
    afw,
    alw,
    alc,
    loa,
    v_curr=0.0,
    dir_curr=0,
    max_wind_test=70,
    step_deg=10,
):
  angles = np.arange(0, 360, step_deg)
  max_safe_winds = []

  if lines_geom_df.empty:
    return list(angles), [0] * len(angles)

  for angle in angles:
    safe_wind = 0
    for v_w in range(1, max_wind_test + 1):
      forces = calculate_environmental_forces(
          v_w, angle, v_curr, dir_curr, afw, alw, alc, loa
      )
      results = solve_line_tensions_3d(lines_geom_df.copy(), forces)
      if (results["Util_Percent"] > 50.0).any():
        break
      safe_wind = v_w
    max_safe_winds.append(safe_wind)

  return list(angles), max_safe_winds


# =============================================================================
# 4. SESSION STATE & RIPRISTINO PORTI RICHIESTI
# =============================================================================
DEFAULT_SHIP = {
    "LOA": 323.6,
    "Beam": 37.2,
    "Draft": 8.2,
    "AFW": 1250.0,
    "ALW": 6120.0,
    "ALC": 1200.0,
}

if "lines_inventory" not in st.session_state:
  st.session_state.lines_inventory = pd.DataFrame([
      {
          "line_id": "1",
          "line_name": "Head Line 1",
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
          "line_name": "Stern Line 1",
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

# RIPRISTINO COMPLETO DEI PORTI RICHIESTI
def_bollards = [
    {
        "bollard_id": "B1",
        "X_Coordinata_m": 170.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B2",
        "X_Coordinata_m": 140.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B3",
        "X_Coordinata_m": 80.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B4",
        "X_Coordinata_m": -80.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B5",
        "X_Coordinata_m": -160.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
]

if "ports_bollards" not in st.session_state:
  st.session_state.ports_bollards = {
      "Long Beach Cruise Terminal": pd.DataFrame(def_bollards),
      "Mazatlan Pier 4/5": pd.DataFrame(def_bollards),
      "Mazatlan Pier 2/3": pd.DataFrame(def_bollards),
      "La Paz": pd.DataFrame(def_bollards),
      "Ensenada Pier #2": pd.DataFrame(def_bollards),
      "Puerto Vallarta Pier #1": pd.DataFrame(def_bollards),
      "Puerto Vallarta Pier #3": pd.DataFrame(def_bollards),
  }

init_db(st.session_state.lines_inventory)

# =============================================================================
# 5. BARRA LATERALE METEO
# =============================================================================
st.sidebar.header("🌐 Condizioni Meteo-Marine")
meteo_mode = st.sidebar.radio(
    "Modalità Meteo:",
    ["Manuale", "Live API (Windy / Open-Meteo)"],
    index=0,
)

selected_port = st.sidebar.selectbox(
    "📌 Porto di Riferimento", list(st.session_state.ports_bollards.keys())
)

if meteo_mode == "Live API (Windy / Open-Meteo)":
  coords = PORT_COORDINATES.get(selected_port, {"lat": 33.7513, "lon": -118.1888})
  success, live_w_speed, live_w_dir = fetch_live_weather(
      coords["lat"], coords["lon"]
  )

  if success:
    st.sidebar.success(f"Meteo Live: {live_w_speed} kts @ {live_w_dir}°")
    v_wind = live_w_speed
    dir_wind = live_w_dir
  else:
    st.sidebar.error("Impossibile contattare il server meteo. Uso manuale.")
    v_wind = st.sidebar.slider("Vento (knots)", 0, 70, 30)
    dir_wind = st.sidebar.slider("Direzione Vento (deg)", 0, 360, 45)
else:
  v_wind = st.sidebar.slider("Vento (knots)", 0, 70, 30)
  dir_wind = st.sidebar.slider("Direzione Vento (deg)", 0, 360, 45)

v_curr = st.sidebar.slider("Corrente (knots)", 0.0, 4.0, 0.5)
dir_curr = st.sidebar.slider("Direzione Corrente (deg)", 0, 360, 0)

# =============================================================================
# 6. INTERFACCIA TABS
# =============================================================================
st.title("⚓ OpenMooring - Live Setup & MEG4 Analysis")

tab_setup, tab_3d_editor, tab_sim, tab_polar, tab_maint = st.tabs([
    "🚢 1. Dati Nave & Cavi",
    "🗺️ 2. Editor 3D Layout Banchina",
    "📊 3. Simulazione Tensioni (in t)",
    "🌀 4. Inviluppo Polare",
    "📈 5. Storico & Usura Cavi",
])

# -----------------------------------------------------------------------------
# TAB 1: DATI NAVE E CAVI
# -----------------------------------------------------------------------------
with tab_setup:
  st.header("🚢 Particulars Nave e Inventario Cavi")

  col_n1, col_n2, col_n3 = st.columns(3)
  with col_n1:
    ship_name = st.text_input("Nome Nave", "Carnival Panorama")
    loa = st.number_input("LOA (m)", value=DEFAULT_SHIP["LOA"], step=0.1)
  with col_n2:
    beam = st.number_input(
        "Larghezza / Beam (m)", value=DEFAULT_SHIP["Beam"], step=0.1
    )
    draft = st.number_input(
        "Pescaggio (m)", value=DEFAULT_SHIP["Draft"], step=0.1
    )
  with col_n3:
    alw = st.number_input(
        "Area Vento Laterale ALW (m²)", value=DEFAULT_SHIP["ALW"], step=10.0
    )
    afw = st.number_input(
        "Area Vento Frontale AFW (m²)", value=DEFAULT_SHIP["AFW"], step=10.0
    )

  ship_dict = {
      "LOA": loa,
      "Beam": beam,
      "Draft": draft,
      "ALW": alw,
      "AFW": afw,
      "ALC": DEFAULT_SHIP["ALC"],
  }

  st.subheader("📋 Gestione Cavi (Valori MBL in Tonnellate [t])")
  edited_lines = st.data_editor(
      st.session_state.lines_inventory,
      num_rows="dynamic",
      use_container_width=True,
      key="lines_editor",
  )
  st.session_state.lines_inventory = edited_lines

# -----------------------------------------------------------------------------
# TAB 2: EDITOR GRAFICO 3D BANCHINA
# -----------------------------------------------------------------------------
with tab_3d_editor:
  st.header(f"🗺️ Layout Banchina & Bitte: {selected_port}")
  st.info(
      "ℹ️ **Coordinata Z Bitta:** indica la quota verticale relativa"
      " rispetto alla Mooring Station della nave."
  )

  df_bollards = st.session_state.ports_bollards[selected_port]

  col_ed_left, col_ed_right = st.columns([1, 1])

  with col_ed_left:
    st.subheader("⚙️ Regolazione Bitta")

    b_id_list = df_bollards["bollard_id"].tolist()
    b_id = st.selectbox("Bitta da modificare:", b_id_list)
    idx = df_bollards[df_bollards["bollard_id"] == b_id].index[0]

    c1, c2, c3, c4 = st.columns(4)
    x_val = c1.number_input(
        "X (m)",
        value=float(df_bollards.loc[idx, "X_Coordinata_m"]),
        step=1.0,
        key="x_in",
    )
    y_val = c2.number_input(
        "Y (m)",
        value=float(df_bollards.loc[idx, "Y_Coordinata_m"]),
        step=1.0,
        key="y_in",
    )
    z_val = c3.number_input(
        "Z risp. Mooring St. (m)",
        value=float(df_bollards.loc[idx, "Z_Altezza_m"]),
        step=0.5,
        key="z_in",
    )
    swl_val = c4.number_input(
        "SWL (t)",
        value=int(df_bollards.loc[idx, "SWL_Bitta_t"]),
        step=10,
        key="swl_in",
    )

    df_bollards.loc[idx, "X_Coordinata_m"] = x_val
    df_bollards.loc[idx, "Y_Coordinata_m"] = y_val
    df_bollards.loc[idx, "Z_Altezza_m"] = z_val
    df_bollards.loc[idx, "SWL_Bitta_t"] = swl_val

    st.subheader("📋 Tabella Bitte")
    edited_bollards = st.data_editor(
        df_bollards,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{selected_port}",
    )
    st.session_state.ports_bollards[selected_port] = edited_bollards

  with col_ed_right:
    st.subheader("🌐 Visualizzazione Layout 3D")

    fig_setup = go.Figure()

    s_x = [-loa / 2, loa / 2 - 30, loa / 2, loa / 2 - 30, -loa / 2, -loa / 2]
    s_y = [-beam / 2, -beam / 2, 0, beam / 2, beam / 2, -beam / 2]
    s_z = [10.0] * len(s_x)
    fig_setup.add_trace(
        go.Scatter3d(
            x=s_x,
            y=s_y,
            z=s_z,
            mode="lines",
            line=dict(color="navy", width=5),
            name=f"Scafo ({ship_name})",
        )
    )

    fig_setup.add_trace(
        go.Mesh3d(
            x=[-200, 200, 200, -200],
            y=[18, 18, 45, 45],
            z=[0, 0, 0, 0],
            color="lightgrey",
            opacity=0.5,
            name="Banchina",
        )
    )

    act_b = edited_bollards[edited_bollards["Stato"] == "Attivo"]
    fig_setup.add_trace(
        go.Scatter3d(
            x=act_b["X_Coordinata_m"],
            y=act_b["Y_Coordinata_m"],
            z=act_b["Z_Altezza_m"],
            mode="markers+text",
            marker=dict(
                size=9,
                color=act_b["SWL_Bitta_t"],
                colorscale="Viridis",
                colorbar=dict(title="SWL (t)"),
                showscale=True,
            ),
            text=[
                f"{r['bollard_id']} ({r['SWL_Bitta_t']}t)"
                for _, r in act_b.iterrows()
            ],
            textposition="top center",
            name="Bitte",
        )
    )

    fig_setup.update_layout(
        scene=dict(
            aspectmode="data",
            xaxis_title="X (m)",
            yaxis_title="Y (m)",
            zaxis_title="Z (m)",
        ),
        margin=dict(l=0, r=0, b=0, t=30),
        height=520,
    )
    st.plotly_chart(fig_setup, use_container_width=True)

# Calcolo geometria aggiornata
active_bollards_df = st.session_state.ports_bollards[selected_port]
geom_df = calculate_line_geometry(
    st.session_state.lines_inventory, active_bollards_df
)

# -----------------------------------------------------------------------------
# TAB 3: SIMULAZIONE TENSIONI
# -----------------------------------------------------------------------------
with tab_sim:
  if geom_df.empty:
    st.error("⚠️ Nessuna corrispondenza trovata tra le bitte dei cavi e della banchina.")
  else:
    forces = calculate_environmental_forces(
        v_wind,
        dir_wind,
        v_curr,
        dir_curr,
        ship_dict["AFW"],
        ship_dict["ALW"],
        ship_dict["ALC"],
        ship_dict["LOA"],
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

    fig_sim = go.Figure()
    s_x = [-loa / 2, loa / 2 - 30, loa / 2, loa / 2 - 30, -loa / 2, -loa / 2]
    s_y = [-beam / 2, -beam / 2, 0, beam / 2, beam / 2, -beam / 2]
    fig_sim.add_trace(
        go.Scatter3d(
            x=s_x,
            y=s_y,
            z=[10.0] * len(s_x),
            mode="lines",
            line=dict(color="navy", width=5),
            name="Nave",
        )
    )

    for _, line in results_df.iterrows():
      util = line["Util_Percent"]
      col_line = (
          "red" if util > 50.0 else ("orange" if util > 35.0 else "green")
      )

      fig_sim.add_trace(
          go.Scatter3d(
              x=[line["chock_x_m"], line["bollard_x_rendered"]],
              y=[line["chock_y_m"], line["bollard_y_rendered"]],
              z=[line["chock_z_m"], line["bollard_z_rendered"]],
              mode="lines+markers",
              line=dict(color=col_line, width=5),
              name=f"{line['line_name']} ({line['Tension_tons']:.1f}t /"
              f" {util:.1f}%)",
          )
      )

    fig_sim.update_layout(
        scene=dict(aspectmode="data"), margin=dict(l=0, r=0, b=0, t=20)
    )
    st.plotly_chart(fig_sim, use_container_width=True)

    st.subheader("Carico Sulle Linee d'Ormeggio (% MBL)")
    fig_bar = px.bar(
        results_df,
        x="line_name",
        y="Util_Percent",
        color="Util_Percent",
        color_continuous_scale=["green", "yellow", "red"],
        range_color=[0, 100],
    )
    fig_bar.add_hline(
        y=50,
        line_dash="dash",
        line_color="red",
        annotation_text="Limite MEG4 (50%)",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    st.dataframe(
        results_df[[
            "line_name",
            "bollard_id",
            "length_m",
            "azimuth_deg",
            "incline_deg",
            "Tension_tons",
            "Util_Percent",
        ]]
    )

# -----------------------------------------------------------------------------
# TAB 4: INVILUPPO POLARE
# -----------------------------------------------------------------------------
with tab_polar:
  st.subheader("Inviluppo Polare dei Limiti Operativi del Vento (0-360°)")

  if st.button("Esegui Simulazione Polare") and not geom_df.empty:
    with st.spinner("Calcolo dinamico in corso..."):
      angles, max_winds = calculate_wind_operability_envelope(
          geom_df,
          ship_dict["AFW"],
          ship_dict["ALW"],
          ship_dict["ALC"],
          ship_dict["LOA"],
          v_curr=v_curr,
          dir_curr=dir_curr,
      )

      fig_polar = go.Figure()
      fig_polar.add_trace(
          go.Scatterpolar(
              r=max_winds,
              theta=angles,
              fill="toself",
              fillcolor="rgba(0, 128, 0, 0.25)",
              line=dict(color="green", width=2),
          )
      )

      max_r = max(max_winds) + 10 if max_winds and len(max_winds) > 0 else 80

      fig_polar.update_layout(
          polar=dict(
              radialaxis=dict(
                  visible=True, range=[0, max_r], ticksuffix=" kts"
              ),
              angularaxis=dict(direction="clockwise", rotation=90),
          ),
          margin=dict(l=40, r=40, t=20, b=20),
      )
      st.plotly_chart(fig_polar, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 5: STORICO & USURA CAVI
# -----------------------------------------------------------------------------
with tab_maint:
  st.subheader("📈 Registro Storico Usura & Suggerimento Sostituzione Cavi")

  c_m1, c_m2 = st.columns([1, 2])

  with c_m1:
    st.write("### Registra Sessione Ormeggio")
    duration_h = st.number_input(
        "Durata Ormeggio (Ore)", min_value=1.0, max_value=72.0, value=12.0
    )
    if st.button("Salva e Aggiorna Database Cavi"):
      if "results_df" in locals():
        log_mooring_session(
            results_df, selected_port, duration_hours=duration_h
        )
        st.success("Sessione salvata nello storico SQLite!")
      else:
        st.warning("Esegui prima la simulazione nel Tab 3.")

  with c_m2:
    st.write("### Stato Salute Cavi e Raccomandazioni")
    health_df = get_lines_health_status()
    if not health_df.empty:
      fig_health = px.bar(
          health_df,
          x="line_name",
          y="Health_Percent",
          color="Health_Percent",
          color_continuous_scale=["red", "yellow", "green"],
          range_color=[0, 100],
      )
      fig_health.add_hline(
          y=20,
          line_dash="dash",
          line_color="red",
          annotation_text="Soglia Sostituzione (20%)",
      )
      st.plotly_chart(fig_health, use_container_width=True)

      st.dataframe(
          health_df[[
              "line_name",
              "accumulated_hours",
              "high_load_hours",
              "Health_Percent",
              "Recommendation",
          ]]
      )
