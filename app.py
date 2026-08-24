from datetime import datetime
import io
import re
import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pypdf import PdfReader
import requests
import streamlit as st

# Tenta l'importazione del modulo canvas interattivo
try:
  from streamlit_drawable_canvas import st_canvas

  HAS_CANVAS = True
except ImportError:
  HAS_CANVAS = False

st.set_page_config(
    page_title="OpenMooring MEG4 Pro - Multi-Port & Certificate Manager",
    layout="wide",
)

# Costante di conversione (kN in tonnellate metriche)
KN_TO_TONS = 0.10197162129779

# =============================================================================
# 1. DATABASE & MANUTENZIONE PREDITTIVA (Persistent SQLite Database)
# =============================================================================

DB_PATH = "openmooring.db"

if "db_conn" not in st.session_state:
    st.session_state.db_conn = sqlite3.connect(
        DB_PATH,
        check_same_thread=False
    )
    st.session_state.db_conn.row_factory = sqlite3.Row

def init_db(lines_df=None):
  conn = st.session_state.db_conn
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_history (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            mbl_tons REAL,
            max_design_hours REAL DEFAULT 2000.0,
            accumulated_hours REAL DEFAULT 0.0,
            high_load_hours REAL DEFAULT 0.0,
            fatigue_index REAL DEFAULT 0.0,
            cert_id TEXT,
            station_id TEXT,
            winch_id TEXT
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
      try:
        line_id_val = row.get("line_id")
        mbl_val = row.get("mbl_tons")

        if pd.isna(line_id_val) or pd.isna(mbl_val):
          continue

        line_id = str(line_id_val).strip()
        if not line_id:
          continue

        line_name = str(row.get("line_name", f"Line {line_id}")).strip()
        mbl_tons = float(mbl_val)
        cert_id = str(row.get("cert_id", "N/A"))
        station_id = str(row.get("station_id", "N/A"))
        winch_id = str(row.get("winch_id", "N/A"))

        cursor.execute(
            """
                    INSERT OR REPLACE INTO line_history (line_id, line_name, mbl_tons, cert_id, station_id, winch_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
            (line_id, line_name, mbl_tons, cert_id, station_id, winch_id),
        )
      except (ValueError, TypeError):
        continue
  conn.commit()


def log_mooring_session(results_df, port_name, duration_hours=6.0):
  conn = st.session_state.db_conn
  cursor = conn.cursor()
  now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  for _, row in results_df.iterrows():
    try:
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
    except Exception:
      continue
  conn.commit()


def get_lines_health_status():
  conn = st.session_state.db_conn
  df = pd.read_sql_query("SELECT * FROM line_history", conn)

  if df.empty:
    return df

  health_percent = []
  recommendations = []

  for _, row in df.iterrows():
    max_h = row["max_design_hours"] if row["max_design_hours"] > 0 else 2000.0
    hours_used_pct = (row["accumulated_hours"] / max_h) * 100.0
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
# 2. INTEGRATORE CERTIFICATI CAVI (PDF READ + PARSER REGEX)
# =============================================================================
def extract_text_from_pdf(pdf_file):
  try:
    reader = PdfReader(pdf_file)
    extracted_text = ""
    for page in reader.pages:
      text = page.extract_text()
      if text:
        extracted_text += text + "\n"
    return extracted_text
  except Exception as e:
    st.error(f"Errore nella lettura del PDF: {e}")
    return ""


def parse_certificate_text(text):
  data = {
      "cert_id": None,
      "manufacturer": None,
      "material": None,
      "diameter_mm": None,
      "mbl_tons": None,
      "length_m": None,
      "standard": None,
  }

  cert_match = re.search(
      r"(?:Certificat[eo]|Cert\.?|Certificate No\.?)\s*[:#]?\s*([A-Za-z0-9\-/]+)",
      text,
      re.IGNORECASE,
  )
  if cert_match:
    data["cert_id"] = cert_match.group(1).strip()

  mfg_match = re.search(
      r"(?:Manufacturer|Costruttore|Maker)\s*[:#]?\s*([A-Za-z0-9\s]+)",
      text,
      re.IGNORECASE,
  )
  if mfg_match:
    data["manufacturer"] = mfg_match.group(1).strip()

  mat_match = re.search(
      r"\b(HMPE|Dyneema|Polyester|Polypropylene|Nylon|Wire|Steel|Aramid)\b",
      text,
      re.IGNORECASE,
  )
  if mat_match:
    data["material"] = mat_match.group(1).upper()

  dia_match = re.search(
      r"(?:Diameter|Diametro|Dia\.?)\s*[:#]?\s*(\d+(?:\.\d+)?)\s*mm",
      text,
      re.IGNORECASE,
  )
  if dia_match:
    data["diameter_mm"] = float(dia_match.group(1))

  mbl_kn_match = re.search(
      r"(?:MBL|Breaking Load|Carico di Rottura)\s*[:#]?\s*(\d+(?:\.\d+)?)\s*kN",
      text,
      re.IGNORECASE,
  )
  mbl_t_match = re.search(
      r"(?:MBL|Breaking Load|Carico di Rottura)\s*[:#]?\s*(\d+(?:\.\d+)?)\s*(?:Tons|t|MT)",
      text,
      re.IGNORECASE,
  )

  if mbl_kn_match:
    data["mbl_tons"] = round(float(mbl_kn_match.group(1)) * KN_TO_TONS, 2)
  elif mbl_t_match:
    data["mbl_tons"] = float(mbl_t_match.group(1))

  std_match = re.search(
      r"\b(MEG4|ISO\s*\d+|DNV|Lloyd'?s\s*Register|ABS|BV)\b",
      text,
      re.IGNORECASE,
  )
  if std_match:
    data["standard"] = std_match.group(1)

  return data


# =============================================================================
# 3. COORDINATE PORTO & METEO AUTOMATICO
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
# 4. MOTORE FISICO & GEOMETRICO
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

  return merged.reset_index(drop=True)


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
    utilizations.append((t / item["mbl"]) * 100.0 if item["mbl"] > 0 else 0.0)

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
    max_wind_test=80,
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

      line_overload = (results["Util_Percent"] > 50.0).any()

      bollard_loads = results.groupby("bollard_id")["Tension_tons"].sum()
      bollard_overload = False
      for b_id, load in bollard_loads.items():
        swl_rows = results[results["bollard_id"] == b_id]["SWL_Bitta_t"]
        if not swl_rows.empty:
          swl = float(swl_rows.iloc[0])
          if load > swl:
            bollard_overload = True
            break

      if line_overload or bollard_overload:
        break
      safe_wind = v_w
    max_safe_winds.append(safe_wind)

  return list(angles), max_safe_winds


# =============================================================================
# 5. SESSION STATE & INIZIALIZZAZIONE DATI
# =============================================================================
DEFAULT_SHIP = {
    "LOA": 323.6,
    "Beam": 37.2,
    "Draft": 8.2,
    "AFW": 1250.0,
    "ALW": 6120.0,
    "ALC": 1200.0,
}

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
      {
          "cert_id": "CERT-TAIL-2025-A1",
          "manufacturer": "Lankhorst",
          "material": "Polyester",
          "diameter_mm": 72,
          "mbl_tons": 100.0,
          "standard": "MEG4",
          "issue_date": "2025-03-01",
      },
  ])

if "mooring_stations" not in st.session_state:
  st.session_state.mooring_stations = {
      "Forward Station (Prua)": pd.DataFrame([
          {
              "winch_id": "W1",
              "winch_type": "Split Drum",
              "chock_id": "C1",
              "chock_x_m": 150.0,
              "chock_y_m": 2.0,
              "chock_z_m": 12.0,
              "brake_holding_tons": 84.0,
          },
          {
              "winch_id": "W2",
              "winch_type": "Split Drum",
              "chock_id": "C2",
              "chock_x_m": 150.0,
              "chock_y_m": -2.0,
              "chock_z_m": 12.0,
              "brake_holding_tons": 84.0,
          },
          {
              "winch_id": "W3",
              "winch_type": "Single Drum",
              "chock_id": "C3",
              "chock_x_m": 138.0,
              "chock_y_m": 18.0,
              "chock_z_m": 10.0,
              "brake_holding_tons": 84.0,
          },
          {
              "winch_id": "W4",
              "winch_type": "Single Drum",
              "chock_id": "C4",
              "chock_x_m": 110.0,
              "chock_y_m": 18.0,
              "chock_z_m": 8.0,
              "brake_holding_tons": 84.0,
          },
      ]),
      "Aft Station (Poppa)": pd.DataFrame([
          {
              "winch_id": "W5",
              "winch_type": "Single Drum",
              "chock_id": "C5",
              "chock_x_m": -110.0,
              "chock_y_m": 18.0,
              "chock_z_m": 8.0,
              "brake_holding_tons": 84.0,
          },
          {
              "winch_id": "W6",
              "winch_type": "Split Drum",
              "chock_id": "C6",
              "chock_x_m": -138.0,
              "chock_y_m": 18.0,
              "chock_z_m": 10.0,
              "brake_holding_tons": 84.0,
          },
          {
              "winch_id": "W7",
              "winch_type": "Split Drum",
              "chock_id": "C7",
              "chock_x_m": -150.0,
              "chock_y_m": 0.0,
              "chock_z_m": 12.0,
              "brake_holding_tons": 84.0,
          },
      ]),
  }

if "lines_inventory" not in st.session_state:
  st.session_state.lines_inventory = pd.DataFrame([
      {
          "line_id": "1",
          "line_name": "Head Line 1",
          "line_type": "Head",
          "station_id": "Forward Station (Prua)",
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
          "station_id": "Forward Station (Prua)",
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
          "station_id": "Forward Station (Prua)",
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
          "station_id": "Forward Station (Prua)",
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
          "station_id": "Aft Station (Poppa)",
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
          "station_id": "Aft Station (Poppa)",
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
          "station_id": "Aft Station (Poppa)",
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

def_bollards = [
    {
        "bollard_id": "B1",
        "Posizione": "Prua",
        "Dist_Estrema_m": 8.2,
        "X_Coordinata_m": 153.6,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B2",
        "Posizione": "Prua",
        "Dist_Estrema_m": 21.8,
        "X_Coordinata_m": 140.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B3",
        "Posizione": "Prua",
        "Dist_Estrema_m": 81.8,
        "X_Coordinata_m": 80.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B4",
        "Posizione": "Poppa",
        "Dist_Estrema_m": 81.8,
        "X_Coordinata_m": -80.0,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B5",
        "Posizione": "Poppa",
        "Dist_Estrema_m": 1.8,
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
# 6. BARRA LATERALE METEO
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

current_berth_heading = st.session_state.port_headings.get(selected_port, 0.0)

if meteo_mode == "Live API (Windy / Open-Meteo)":
  coords = PORT_COORDINATES.get(selected_port, {"lat": 33.7513, "lon": -118.1888})
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
# 7. INTERFACCIA TABS
# =============================================================================
st.title("⚓ OpenMooring - MEG4 Pro Suite")

(
    tab_setup,
    tab_certs,
    tab_stations,
    tab_3d_editor,
    tab_sim,
    tab_polar,
    tab_maint,
) = st.tabs([
    "🚢 1. Dati Nave & Inventario",
    "📜 2. Certificati Cavi (PDF Drag & Drop)",
    "🏗️ 3. Pianetti Mooring Stations",
    "🗺️ 4. Layout Banchina & Bitte",
    "📊 5. Simulazione Tensioni",
    "🌀 6. Inviluppo Polare",
    "📈 7. Storico & Usura Cavi",
])

# -----------------------------------------------------------------------------
# TAB 1: DATI NAVE E CAVI
# -----------------------------------------------------------------------------
with tab_setup:
  st.header("🚢 Particulars Nave e Inventario Cavi Attivi")

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

  st.subheader("📋 Inventario Cavi & Mappatura")
  edited_lines = st.data_editor(
      st.session_state.lines_inventory,
      num_rows="dynamic",
      use_container_width=True,
      key="lines_editor",
  )
  st.session_state.lines_inventory = edited_lines

# -----------------------------------------------------------------------------
# TAB 2: CERTIFICATI CAVI (DRAG & DROP PDF + PARSING AUTOMATICO)
# -----------------------------------------------------------------------------
with tab_certs:
  st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
  st.info(
      "📁 **Drag & Drop Certificato:** Trascina direttamente il file PDF del"
      " certificato del cavo. Il sistema estrarrà il testo, eseguirà il parsing"
      " Regex di MBL, Diametro e Costruttore e lo salverà nel database."
  )

  c_col1, c_col2 = st.columns([1, 1])

  with c_col1:
    st.subheader("📤 Carica File PDF Certificato")
    uploaded_pdf = st.file_uploader(
        "Trascina qui il file PDF del Certificato",
        type=["pdf"],
        help="Carica il file PDF inviato dal produttore del cavo",
    )

    cert_text_to_parse = ""

    if uploaded_pdf is not None:
      st.success(f"File caricato: {uploaded_pdf.name}")
      cert_text_to_parse = extract_text_from_pdf(uploaded_pdf)
      with st.expander("📄 Testo estratto dal PDF"):
        st.text_area(
            "Anteprima Testo", cert_text_to_parse, height=150, disabled=True
        )

    st.subheader("📝 Inserimento Manuale Alternate")
    manual_text = st.text_area(
        "Oppure incolla qui il testo del certificato",
        height=100,
        placeholder="Certificate No: CERT-2026-X ...",
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

        # Aggiornamento/Inserimento nel DB
        st.session_state.certificates_db = pd.concat(
            [st.session_state.certificates_db, pd.DataFrame([new_cert])],
            ignore_index=True,
        ).drop_duplicates(subset=["cert_id"], keep="last")

        st.success(f"Certificato {new_cert_id} salvato nel database!")
        st.rerun()

  with c_col2:
    st.subheader("📚 Database Certificati Registrati")
    st.dataframe(
        st.session_state.certificates_db,
        use_container_width=True,
        height=280,
    )

    st.subheader("🔗 Associa Certificato a Linea d'Ormeggio")
    col_sel1, col_sel2 = st.columns(2)
    selected_line = col_sel1.selectbox(
        "Seleziona Linea", st.session_state.lines_inventory["line_name"]
    )
    selected_cert = col_sel2.selectbox(
        "Seleziona Certificato", st.session_state.certificates_db["cert_id"]
    )

    if st.button("🔗 Applica Certificato a Linea"):
      cert_row = st.session_state.certificates_db[
          st.session_state.certificates_db["cert_id"] == selected_cert
      ].iloc[0]
      idx = st.session_state.lines_inventory[
          st.session_state.lines_inventory["line_name"] == selected_line
      ].index

      if not idx.empty:
        st.session_state.lines_inventory.loc[idx[0], "cert_id"] = selected_cert
        st.session_state.lines_inventory.loc[idx[0], "mbl_tons"] = cert_row[
            "mbl_tons"
        ]
        st.session_state.lines_inventory.loc[idx[0], "diameter_mm"] = cert_row[
            "diameter_mm"
        ]
        st.session_state.lines_inventory.loc[idx[0], "material"] = cert_row[
            "material"
        ]
        st.success(
            f"Linea '{selected_line}' aggiornata con MBL ({cert_row['mbl_tons']}t)"
            f" dal certificato {selected_cert}!"
        )
        st.rerun()

# -----------------------------------------------------------------------------
# TAB 3: MOORING STATIONS, DOWNLOAD PIANETTI & ANNOTAZIONE INTERATTIVA
# -----------------------------------------------------------------------------
with tab_stations:
  st.header("🏗️ Mappatura Stazioni d'Ormeggio, Pianetti & Annotazione")

  station_sel = st.selectbox(
      "Seleziona Stazione d'Ormeggio",
      list(st.session_state.mooring_stations.keys()),
  )
  st_df = st.session_state.mooring_stations[station_sel]

  st.subheader(f"⚙️ Configurazione Dati: {station_sel}")
  edited_st = st.data_editor(
      st_df,
      num_rows="dynamic",
      use_container_width=True,
      key=f"edit_st_{station_sel}",
  )
  st.session_state.mooring_stations[station_sel] = edited_st

  # Generazione Figura Grafica Pianetto
  fig_st = go.Figure()

  # Disegno dei guidacavi / chocks / verricelli
  fig_st.add_trace(
      go.Scatter(
          x=edited_st["chock_x_m"],
          y=edited_st["chock_y_m"],
          mode="markers+text",
          marker=dict(size=18, color="darkorange", symbol="square"),
          text=edited_st["winch_id"] + " (" + edited_st["chock_id"] + ")",
          textposition="top center",
          name="Winch / Chock Position",
      )
  )

  fig_st.update_layout(
      title=f"Pianetto Grafico Vetrina - {station_sel}",
      xaxis_title="Coordinata X Longitudinale (m)",
      yaxis_title="Coordinata Y Trasversale (m)",
      height=380,
  )

  col_plan1, col_plan2 = st.columns([1, 1])

  with col_plan1:
    st.plotly_chart(fig_st, use_container_width=True)

    # Export Pianetto in HTML / Formato Immagine
    buffer = io.StringIO()
    fig_st.write_html(buffer, include_plotlyjs="cdn")
    html_bytes = buffer.getvalue().encode()

    st.download_button(
        label="💾 Scarica Pianetto (Interactive HTML)",
        data=html_bytes,
        file_name=f"pianetto_{station_sel.replace(' ', '_')}.html",
        mime="text/html",
    )

  with col_plan2:
    st.subheader("🖌️ Identificazione & Annotazione Manuale Pianetto")
    st.write(
        "Disegna o annota a mano sul canvas sottostante per identificare verricelli,"
        " tamburi e numeri cavo:"
    )

    if HAS_CANVAS:
      drawing_mode = st.selectbox(
          "Strumento di Disegno:",
          ["freedraw", "circle", "rect", "line", "transform"],
      )
      stroke_color = st.color_picker("Colore Penna", "#FF0000")
      stroke_width = st.slider("Spessore Penna", 1, 10, 3)

      canvas_result = st_canvas(
          fill_color="rgba(255, 165, 0, 0.3)",
          stroke_width=stroke_width,
          stroke_color=stroke_color,
          background_color="#f0f2f6",
          height=300,
          width=500,
          drawing_mode=drawing_mode,
          key=f"canvas_{station_sel}",
      )
    else:
      st.warning(
          "Modulo `streamlit-drawable-canvas` non installato. Per abilitare la"
          " lavagna interattiva esegui: `pip install streamlit-drawable-canvas`"
      )

# -----------------------------------------------------------------------------
# TAB 4: EDITOR BITTE CON MISURE RANGEFINDER (PRUA / POPPA) & ALLINEAMENTO BANCHINA
# -----------------------------------------------------------------------------
with tab_3d_editor:
  st.header(f"🗺️ Layout Banchina & Bitte: {selected_port}")
  st.info(
      "📏 **Misurazione Banchina (Rangefinder):** Le coordinate X sono inserite"
      " come **distanza dall'estrema prua** (per bitte a prua) o **dall'estrema"
      " poppa** (per bitte a poppa)."
  )

  st.subheader("📐 Orientamento e Allineamento Banchina")
  berth_heading = st.number_input(
      "Orientamento Banchina / Berth True Heading (° True)",
      min_value=0.0,
      max_value=360.0,
      value=float(st.session_state.port_headings.get(selected_port, 135.0)),
      step=1.0,
      key=f"heading_input_{selected_port}",
  )
  st.session_state.port_headings[selected_port] = berth_heading

  st.divider()

  df_bollards = st.session_state.ports_bollards[selected_port]

  st.subheader("➕ Aggiungi Bitta alla Banchina")
  c_add1, c_add2, c_add3, c_add4, c_add5, c_add6 = st.columns(6)

  new_b_id = c_add1.text_input("ID Bitta", f"B{len(df_bollards) + 1}")
  new_pos = c_add2.selectbox("Zona Bitta", ["Prua", "Poppa"])
  new_dist = c_add3.number_input("Dist. Estrema (m)", min_value=0.0, value=15.0)
  new_y = c_add4.number_input("Dist. Banchina Y (m)", value=25.0)
  new_z = c_add5.number_input("Altezza Z (m)", value=-3.0)
  new_swl = c_add6.number_input("SWL Bitta (t)", value=150)

  col_btn1, col_btn2 = st.columns(2)

  if col_btn1.button("➕ Aggiungi Bitta a Prua"):
    x_abs = (loa / 2.0) - new_dist
    new_row = {
        "bollard_id": new_b_id,
        "Posizione": "Prua",
        "Dist_Estrema_m": new_dist,
        "X_Coordinata_m": x_abs,
        "Y_Coordinata_m": new_y,
        "Z_Altezza_m": new_z,
        "SWL_Bitta_t": new_swl,
        "Stato": "Attivo",
    }
    st.session_state.ports_bollards[selected_port] = pd.concat(
        [df_bollards, pd.DataFrame([new_row])], ignore_index=True
    )
    st.rerun()

  if col_btn2.button("➕ Aggiungi Bitta a Poppa"):
    x_abs = -(loa / 2.0) + new_dist
    new_row = {
        "bollard_id": new_b_id,
        "Posizione": "Poppa",
        "Dist_Estrema_m": new_dist,
        "X_Coordinata_m": x_abs,
        "Y_Coordinata_m": new_y,
        "Z_Altezza_m": new_z,
        "SWL_Bitta_t": new_swl,
        "Stato": "Attivo",
    }
    st.session_state.ports_bollards[selected_port] = pd.concat(
        [df_bollards, pd.DataFrame([new_row])], ignore_index=True
    )
    st.rerun()

  st.divider()

  df_curr = st.session_state.ports_bollards[selected_port].copy()
  calc_x = []
  for _, r in df_curr.iterrows():
    if r.get("Posizione") == "Prua":
      calc_x.append((loa / 2.0) - float(r.get("Dist_Estrema_m", 0)))
    else:
      calc_x.append(-(loa / 2.0) + float(r.get("Dist_Estrema_m", 0)))
  df_curr["X_Coordinata_m"] = calc_x

  col_ed_left, col_ed_right = st.columns([1, 1])

  with col_ed_left:
    st.subheader("📋 Tabella Bitte Banchina")
    edited_bollards = st.data_editor(
        df_curr,
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
                showscale=True,
            ),
            text=[
                f"{r['bollard_id']} ({r['Posizione']}: {r['Dist_Estrema_m']}m,"
                f" SWL:{r['SWL_Bitta_t']}t)"
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

# Calcolo della geometria
active_bollards_df = st.session_state.ports_bollards[selected_port]
geom_df = calculate_line_geometry(
    st.session_state.lines_inventory, active_bollards_df
)

# -----------------------------------------------------------------------------
# TAB 5: SIMULAZIONE TENSIONI
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
            "cert_id",
            "bollard_id",
            "length_m",
            "azimuth_deg",
            "incline_deg",
            "Tension_tons",
            "Util_Percent",
        ]]
    )

    if st.button("💾 Registra Sessione d'Ormeggio nel DB"):
      log_mooring_session(results_df, selected_port)
      st.success("Sessione salvata con successo nello storico usura!")

# -----------------------------------------------------------------------------
# TAB 6: INVILUPPO POLARE
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
# TAB 7: STORICO & USURA CAVI
# -----------------------------------------------------------------------------
with tab_maint:
  st.subheader("📈 Registro Storico Usura & Suggerimento Sostituzione Cavi")

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
            "line_id",
            "line_name",
            "cert_id",
            "accumulated_hours",
            "high_load_hours",
            "Health_Percent",
            "Recommendation",
        ]]
    )
