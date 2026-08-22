import sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# =============================================================================
# 1. DATABASE & MANUTENZIONE PREDITTIVA (MOORING DB)
# =============================================================================
DB_NAME = "mooring_history.db"


def init_db(lines_df=None):
  """Inizializza il database SQLite locale e registra i cavi se non presenti."""
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_history (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            mbl_kN REAL,
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
            tension_kN REAL,
            util_percent REAL,
            duration_hours REAL
        )
    """)

  if lines_df is not None:
    for _, row in lines_df.iterrows():
      cursor.execute(
          """
                INSERT OR IGNORE INTO line_history (line_id, line_name, mbl_kN)
                VALUES (?, ?, ?)
            """,
          (str(row["line_id"]), str(row["line_name"]), float(row["mbl_kN"])),
      )

  conn.commit()
  conn.close()


def log_mooring_session(results_df, port_name, duration_hours=6.0):
  """Registra l'ormeggio e aggiorna l'indice di fatica e usura dei cavi."""
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  for _, row in results_df.iterrows():
    line_id = str(row["line_id"])
    tension = float(row["Tension_kN"])
    util = float(row["Util_Percent"])

    cursor.execute(
        """
            INSERT INTO mooring_logs (timestamp, port_name, line_id, tension_kN, util_percent, duration_hours)
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
  """Calcola lo stato di salute residua dei cavi e fornisce raccomandazioni MEG4."""
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
# 2. MOTORE FISICO, GEOMETRICO E CALCOLO POLARE (MOORING MATH)
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
  """Calcola forze (Fx, Fy) e momento (Mz) da vento e corrente (Formule OCIMF)."""
  v_wind = v_wind_knots * 0.514444  # knots -> m/s
  v_curr = v_curr_knots * 0.514444
  rho_air = 1.225
  rho_water = 1025.0

  rad_wind = np.radians(dir_wind_deg)
  rad_curr = np.radians(dir_curr_deg)

  cx_w = -np.cos(rad_wind)
  cy_w = np.sin(rad_wind)
  cmz_w = 0.15 * np.sin(2 * rad_wind)

  cx_c = -0.5 * np.cos(rad_curr)
  cy_c = np.sin(rad_curr)
  cmz_c = 0.1 * np.sin(2 * rad_curr)

  fx_w = 0.5 * rho_air * (v_wind**2) * afw * cx_w / 1000.0
  fy_w = 0.5 * rho_air * (v_wind**2) * alw * cy_w / 1000.0
  mz_w = 0.5 * rho_air * (v_wind**2) * alw * loa * cmz_w / 1000.0

  fx_c = 0.5 * rho_water * (v_curr**2) * afw * 0.1 * cx_c / 1000.0
  fy_c = 0.5 * rho_water * (v_curr**2) * alc * cy_c / 1000.0
  mz_c = 0.5 * rho_water * (v_curr**2) * alc * loa * cmz_c / 1000.0

  return {
      "Fx_total": fx_w + fx_c,
      "Fy_total": fy_w + fy_c,
      "Mz_total": mz_w + mz_c,
  }


def calculate_line_geometry(lines_df, bollards_df):
  """Calcola lunghezza 3D, azimut e inclinazione per ciascuna linea d'ormeggio."""
  merged = pd.merge(
      lines_df, bollards_df, on="bollard_id", suffixes=("_chock", "_bollard")
  )

  dx = merged["bollard_x_m"] - merged["chock_x_m"]
  dy = merged["bollard_y_m"] - merged["chock_y_m"]
  dz = merged["bollard_z_m"] - merged["chock_z_m"]

  length_3d = np.sqrt(dx**2 + dy**2 + dz**2)
  length_2d = np.sqrt(dx**2 + dy**2)

  azimuth_deg = np.degrees(np.arctan2(dy, dx)) % 360
  incline_deg = np.degrees(np.arctan2(np.abs(dz), length_2d))

  merged["length_m"] = length_3d
  merged["azimuth_deg"] = azimuth_deg
  merged["incline_deg"] = incline_deg

  return merged


def calculate_composite_stiffness(line):
  """Calcola la rigidezza equivalente in serie (Cavo + Coda sintetica)."""
  length_tail = line.get("tail_length_m", 0.0)
  length_main = max(0.1, line["length_m"] - length_tail)
  area_main = np.pi * ((line["diameter_mm"] / 1000.0) ** 2) / 4.0
  k_main = (line["E_modulus_GPa"] * 1e6 * area_main) / length_main

  if length_tail <= 0 or line.get("tail_diameter_mm", 0) <= 0:
    return k_main, line["mbl_kN"]

  area_tail = np.pi * ((line["tail_diameter_mm"] / 1000.0) ** 2) / 4.0
  k_tail = (line["tail_E_modulus_GPa"] * 1e6 * area_tail) / length_tail

  k_eq = (k_main * k_tail) / (k_main + k_tail)
  effective_mbl = min(line["mbl_kN"], line.get("tail_mbl_kN", line["mbl_kN"]))

  return k_eq, effective_mbl


def solve_line_tensions_3d(lines_geom_df, forces):
  """Risolve il sistema matriciale delle forze ed estrae il carico sui cavi (% MBL)."""
  K_global = np.zeros((3, 3))
  F_ext = np.array(
      [forces["Fx_total"], forces["Fy_total"], forces["Mz_total"]]
  )
  line_data = []

  for _, line in lines_geom_df.iterrows():
    rad_az = np.radians(line["azimuth_deg"])
    rad_inc = np.radians(line["incline_deg"])

    dx = np.cos(rad_inc) * np.cos(rad_az)
    dy = np.cos(rad_inc) * np.sin(rad_az)

    k_eq, effective_mbl = calculate_composite_stiffness(line)

    rx, ry = line["chock_x_m"], line["chock_y_m"]
    m_z = rx * dy - ry * dx

    b = np.array([dx, dy, m_z])
    K_global += k_eq * np.outer(b, b)

    line_data.append({"k": k_eq, "b": b, "mbl": effective_mbl})

  try:
    displacements = np.linalg.solve(K_global, F_ext)
  except np.linalg.LinAlgError:
    displacements = np.zeros(3)

  tensions = []
  utilizations = []

  for item in line_data:
    t = item["k"] * np.dot(item["b"], displacements)
    t_pos = max(0.0, t)
    tensions.append(t_pos)
    utilizations.append((t_pos / item["mbl"]) * 100.0)

  lines_geom_df["Tension_kN"] = tensions
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
  """Simula la velocità massima del vento sostenibile prima che un cavo superi il 50% MBL."""
  angles = np.arange(0, 360, step_deg)
  max_safe_winds = []

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

  return angles, max_safe_winds


def create_mooring_3d_plot(results_df, bollards_df, loa=323.0, beam=37.2):
  """Crea la rappresentazione grafica 3D del layout d'ormeggio con Plotly."""
  fig = go.Figure()

  # Sagoma Schematica Nave
  ship_x = [-loa / 2, loa / 2 - 30, loa / 2, loa / 2 - 30, -loa / 2, -loa / 2]
  ship_y = [-beam / 2, -beam / 2, 0, beam / 2, beam / 2, -beam / 2]
  ship_z = [10.0] * len(ship_x)

  fig.add_trace(
      go.Scatter3d(
          x=ship_x,
          y=ship_y,
          z=ship_z,
          mode="lines",
          line=dict(color="navy", width=5),
          name="Nave",
      )
  )

  # Bittoni
  fig.add_trace(
      go.Scatter3d(
          x=bollards_df["bollard_x_m"],
          y=bollards_df["bollard_y_m"],
          z=bollards_df["bollard_z_m"],
          mode="markers+text",
          marker=dict(size=6, color="black"),
          text=bollards_df["bollard_id"],
          name="Bittoni",
      )
  )

  # Cavi d'ormeggio
  for _, line in results_df.iterrows():
    util = line["Util_Percent"]
    color = "red" if util > 50.0 else ("orange" if util > 35.0 else "green")

    fig.add_trace(
        go.Scatter3d(
            x=[line["chock_x_m"], line["bollard_x_m"]],
            y=[line["chock_y_m"], line["bollard_y_m"]],
            z=[line["chock_z_m"], line["bollard_z_m"]],
            mode="lines+markers",
            line=dict(color=color, width=4),
            name=f"{line['line_name']} ({util:.1f}%)",
        )
    )

  fig.update_layout(
      scene=dict(aspectmode="data"), margin=dict(l=0, r=0, b=0, t=30)
  )
  return fig


# =============================================================================
# 3. INTERFACCIA STREAMLIT MAIN APP
# =============================================================================
st.set_page_config(page_title="OpenMooring MEG4 Pro", layout="wide")
st.title("⚓ OpenMooring - Analysis & Line Lifetime Management")

# DATI DI DEFAULT FALLBACK
DEFAULT_SHIP = {
    "LOA": 323.0,
    "Beam": 37.2,
    "Draft_Fwd": 8.2,
    "Draft_Aft": 8.4,
    "AFW": 1100.0,
    "ALW": 5200.0,
    "ALC": 1200.0,
}

DEFAULT_LINES = pd.DataFrame([
    {
        "line_id": "1",
        "line_name": "Head Line 1",
        "chock_x_m": 150.0,
        "chock_y_m": 2.0,
        "chock_z_m": 12.0,
        "material": "HMPE",
        "diameter_mm": 64,
        "E_modulus_GPa": 120,
        "mbl_kN": 950,
        "tail_length_m": 11.0,
        "tail_diameter_mm": 72,
        "tail_E_modulus_GPa": 6,
        "tail_mbl_kN": 900,
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
        "mbl_kN": 950,
        "tail_length_m": 11.0,
        "tail_diameter_mm": 72,
        "tail_E_modulus_GPa": 6,
        "tail_mbl_kN": 900,
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
        "mbl_kN": 950,
        "tail_length_m": 11.0,
        "tail_diameter_mm": 72,
        "tail_E_modulus_GPa": 6,
        "tail_mbl_kN": 900,
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
        "mbl_kN": 950,
        "tail_length_m": 0.0,
        "tail_diameter_mm": 0,
        "tail_E_modulus_GPa": 0,
        "tail_mbl_kN": 0,
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
        "mbl_kN": 950,
        "tail_length_m": 0.0,
        "tail_diameter_mm": 0,
        "tail_E_modulus_GPa": 0,
        "tail_mbl_kN": 0,
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
        "mbl_kN": 950,
        "tail_length_m": 11.0,
        "tail_diameter_mm": 72,
        "tail_E_modulus_GPa": 6,
        "tail_mbl_kN": 900,
        "bollard_id": "B5",
    },
])

# ELENCO PORTI AGGIORNATO
DEFAULT_BOLLARDS = pd.DataFrame([
    # Ensenada Pier #2
    {
        "port_name": "Ensenada (pier #2)",
        "bollard_id": "B1",
        "bollard_x_m": 170.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 3.0,
    },
    {
        "port_name": "Ensenada (pier #2)",
        "bollard_id": "B2",
        "bollard_x_m": 140.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 3.0,
    },
    {
        "port_name": "Ensenada (pier #2)",
        "bollard_id": "B3",
        "bollard_x_m": 80.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 3.0,
    },
    {
        "port_name": "Ensenada (pier #2)",
        "bollard_id": "B4",
        "bollard_x_m": -80.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 3.0,
    },
    {
        "port_name": "Ensenada (pier #2)",
        "bollard_id": "B5",
        "bollard_x_m": -160.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 3.0,
    },
    # Long Beach Cruise Terminal
    {
        "port_name": "Long Beach (cruise terminal)",
        "bollard_id": "B1",
        "bollard_x_m": 175.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Long Beach (cruise terminal)",
        "bollard_id": "B2",
        "bollard_x_m": 145.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Long Beach (cruise terminal)",
        "bollard_id": "B3",
        "bollard_x_m": 85.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Long Beach (cruise terminal)",
        "bollard_id": "B4",
        "bollard_x_m": -85.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Long Beach (cruise terminal)",
        "bollard_id": "B5",
        "bollard_x_m": -170.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
    # Mazatlan
    {
        "port_name": "Mazatlan",
        "bollard_id": "B1",
        "bollard_x_m": 165.0,
        "bollard_y_m": 28.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "Mazatlan",
        "bollard_id": "B2",
        "bollard_x_m": 135.0,
        "bollard_y_m": 28.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "Mazatlan",
        "bollard_id": "B3",
        "bollard_x_m": 75.0,
        "bollard_y_m": 24.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "Mazatlan",
        "bollard_id": "B4",
        "bollard_x_m": -75.0,
        "bollard_y_m": 24.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "Mazatlan",
        "bollard_id": "B5",
        "bollard_x_m": -165.0,
        "bollard_y_m": 28.0,
        "bollard_z_m": 2.0,
    },
    # La Paz
    {
        "port_name": "La Paz",
        "bollard_id": "B1",
        "bollard_x_m": 160.0,
        "bollard_y_m": 26.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "La Paz",
        "bollard_id": "B2",
        "bollard_x_m": 130.0,
        "bollard_y_m": 26.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "La Paz",
        "bollard_id": "B3",
        "bollard_x_m": 70.0,
        "bollard_y_m": 22.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "La Paz",
        "bollard_id": "B4",
        "bollard_x_m": -70.0,
        "bollard_y_m": 22.0,
        "bollard_z_m": 2.0,
    },
    {
        "port_name": "La Paz",
        "bollard_id": "B5",
        "bollard_x_m": -160.0,
        "bollard_y_m": 26.0,
        "bollard_z_m": 2.0,
    },
    # Puerto Vallarta Pier #1
    {
        "port_name": "Puerto Vallarta (pier #1)",
        "bollard_id": "B1",
        "bollard_x_m": 170.0,
        "bollard_y_m": 32.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #1)",
        "bollard_id": "B2",
        "bollard_x_m": 140.0,
        "bollard_y_m": 32.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #1)",
        "bollard_id": "B3",
        "bollard_x_m": 80.0,
        "bollard_y_m": 26.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #1)",
        "bollard_id": "B4",
        "bollard_x_m": -80.0,
        "bollard_y_m": 26.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #1)",
        "bollard_id": "B5",
        "bollard_x_m": -170.0,
        "bollard_y_m": 32.0,
        "bollard_z_m": 2.5,
    },
    # Puerto Vallarta Pier #3
    {
        "port_name": "Puerto Vallarta (pier #3)",
        "bollard_id": "B1",
        "bollard_x_m": 172.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #3)",
        "bollard_id": "B2",
        "bollard_x_m": 142.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #3)",
        "bollard_id": "B3",
        "bollard_x_m": 82.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #3)",
        "bollard_id": "B4",
        "bollard_x_m": -82.0,
        "bollard_y_m": 25.0,
        "bollard_z_m": 2.5,
    },
    {
        "port_name": "Puerto Vallarta (pier #3)",
        "bollard_id": "B5",
        "bollard_x_m": -172.0,
        "bollard_y_m": 30.0,
        "bollard_z_m": 2.5,
    },
])

# SCHEDE DELL'APPLICAZIONE
tab_app1, tab_app2, tab_app3, tab_app4 = st.tabs([
    "📂 1. Caricamento CSV",
    "🌐 2. Analisi Ormeggio & Vista 3D",
    "🌀 3. Inviluppo Polare Vento",
    "📈 4. Storico Usura & Manutenzione",
])

# -----------------------------------------------------------------------------
# TAB 1: CARICAMENTO CSV
# -----------------------------------------------------------------------------
with tab_app1:
  st.header("📂 Caricamento File CSV per Nave, Cavi e Banchine")
  col_a, col_b, col_c = st.columns(3)

  with col_a:
    st.subheader("1. Particulars Nave")
    file_ship = st.file_uploader(
        "Carica `ship_particulars.csv`", type=["csv"], key="ship"
    )
    if file_ship:
      df_ship_raw = pd.read_csv(file_ship)
      ship_dict = dict(zip(df_ship_raw["parameter"], df_ship_raw["value"]))
      st.success("CSV Nave caricato!")
    else:
      ship_dict = DEFAULT_SHIP
      st.info("Utilizzo dati nave di default.")

  with col_b:
    st.subheader("2. Inventario Cavi")
    file_lines = st.file_uploader(
        "Carica `lines_inventory.csv`", type=["csv"], key="lines"
    )
    if file_lines:
      lines_df = pd.read_csv(file_lines)
      st.success("CSV Cavi caricato!")
    else:
      lines_df = DEFAULT_LINES
      st.info("Utilizzo cavi di default.")

  with col_c:
    st.subheader("3. Banchine Porti")
    file_ports = st.file_uploader(
        "Carica `ports_database.csv`", type=["csv"], key="ports"
    )
    if file_ports:
      ports_df = pd.read_csv(file_ports)
      st.success("CSV Porti caricato!")
    else:
      ports_df = DEFAULT_BOLLARDS
      st.info("Utilizzo banchine di default.")

  selected_port = st.selectbox(
      "Seleziona Porto per l'Analisi", ports_df["port_name"].unique()
  )
  bollards_df = ports_df[ports_df["port_name"] == selected_port]

  # Inizializza il DB con i dati dei cavi attivi
  init_db(lines_df)

  st.divider()
  st.subheader("Anteprima Dati Attivi")
  st.json(ship_dict)
  st.dataframe(
      lines_df[
          ["line_name", "material", "diameter_mm", "mbl_kN", "bollard_id"]
      ]
  )

# -----------------------------------------------------------------------------
# TAB 2: ANALISI ORMEGGIO & VISTA 3D
# -----------------------------------------------------------------------------
with tab_app2:
  st.sidebar.header("Condizioni Meteo-Marine")
  v_wind = st.sidebar.slider("Vento (knots)", 0, 70, 30)
  dir_wind = st.sidebar.slider("Direzione Vento (deg)", 0, 360, 45)
  v_curr = st.sidebar.slider("Corrente (knots)", 0.0, 4.0, 0.5)
  dir_curr = st.sidebar.slider("Direzione Corrente (deg)", 0, 360, 0)

  geom_df = calculate_line_geometry(lines_df, bollards_df)
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

  st.subheader(f"Layout & Tensioni ad Ormeggio: **{selected_port}**")

  col1, col2, col3 = st.columns(3)
  col1.metric("Forza Longitudinale (Fx)", f"{forces['Fx_total']:.1f} kN")
  col2.metric("Forza Trasversale (Fy)", f"{forces['Fy_total']:.1f} kN")
  col3.metric("Momento Imbardata (Mz)", f"{forces['Mz_total']:.1f} kNm")

  fig_3d = create_mooring_3d_plot(
      results_df, bollards_df, loa=ship_dict["LOA"], beam=ship_dict["Beam"]
  )
  st.plotly_chart(fig_3d, use_container_width=True)

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
          "Tension_kN",
          "Util_Percent",
      ]]
  )

# -----------------------------------------------------------------------------
# TAB 3: INVILUPPO POLARE
# -----------------------------------------------------------------------------
with tab_app3:
  st.subheader("Inviluppo Polare dei Limiti Operativi del Vento (0-360°)")
  st.write(
      "Visualizza la velocità massima del vento sostenibile prima che una linea"
      " superi il **50% MBL**."
  )

  if st.button("Esegui Simulazione Polare"):
    with st.spinner("Calcolo simulazione polare in corso..."):
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
      fig_polar.update_layout(
          polar=dict(
              radialaxis=dict(
                  visible=True, range=[0, max(max_winds) + 10], suffix=" kts"
              ),
              angularaxis=dict(direction="clockwise", rotation=90),
          )
      )
      st.plotly_chart(fig_polar, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 4: STORICO USURA & MANUTENZIONE
# -----------------------------------------------------------------------------
with tab_app4:
  st.subheader("📈 Registro Storico Usura & Suggerimento Sostituzione Cavi")

  col_log1, col_log2 = st.columns([1, 2])

  with col_log1:
    st.write("### Registra Ormeggio Attuale")
    duration_h = st.number_input(
        "Durata Ormeggio (Ore)", min_value=1.0, max_value=72.0, value=12.0
    )
    if st.button("Salva Sessione e Aggiorna Storico Cavi"):
      log_mooring_session(results_df, selected_port, duration_hours=duration_h)
      st.success("Sessione salvata con successo nel database dello storico!")

  with col_log2:
    st.write("### Stato Salute Cavi e Raccomandazioni Sostituzione")
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
