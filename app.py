import os
import re
import json
import math
import shutil
import sqlite3
from datetime import datetime, timezone
from contextlib import contextmanager

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# =============================================================================
# CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="OpenMooring",
    page_icon="⚓",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_TITLE = "⚓ OpenMooring"
DB_FILE = "openmooring.db"
BACKUP_DIR = "backups"

KNOT_TO_MPS = 0.514444
TON_FORCE_TO_KN = 9.80665
KGF_TO_KN = 0.00980665
LBF_TO_KN = 0.0044482216152605

PORT_COORDINATES = {
    "Long Beach Cruise Terminal": {"lat": 33.7513, "lon": -118.1888},
    "Cabo San Lucas": {"lat": 22.8905, "lon": -109.9167},
    "Mazatlan Pier 4/5": {"lat": 23.1994, "lon": -106.4200},
    "Mazatlan Pier 2/3": {"lat": 23.1994, "lon": -106.4200},
    "La Paz": {"lat": 24.1426, "lon": -110.3128},
    "Ensenada Pier #2": {"lat": 31.8667, "lon": -116.6000},
    "Puerto Vallarta Pier #1": {"lat": 20.6534, "lon": -105.2253},
    "Puerto Vallarta Pier #3": {"lat": 20.6534, "lon": -105.2253},
}

DEFAULT_PORT_HEADINGS = {
    "Long Beach Cruise Terminal": 135.0,
    "Cabo San Lucas": 0.0,
    "Mazatlan Pier 4/5": 315.0,
    "Mazatlan Pier 2/3": 135.0,
    "La Paz": 180.0,
    "Ensenada Pier #2": 220.0,
    "Puerto Vallarta Pier #1": 0.0,
    "Puerto Vallarta Pier #3": 0.0,
}


# =============================================================================
# DATABASE
# =============================================================================

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        yield conn
        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def init_db():
    with get_connection() as conn:

        conn.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            cert_id TEXT PRIMARY KEY,
            manufacturer TEXT,
            material TEXT,
            diameter_mm REAL,
            mbl_kn REAL,
            mbl_tons REAL,
            standard TEXT,
            issue_date TEXT,
            expiry_date TEXT,
            source_text TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS mooring_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_name TEXT UNIQUE NOT NULL,
            station TEXT,
            line_type TEXT,
            material TEXT,
            diameter_mm REAL,
            length_m REAL,
            mbl_kn REAL,
            mbl_tons REAL,
            cert_id TEXT,
            brake_holding_capacity_kn REAL,
            condition TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(cert_id) REFERENCES certificates(cert_id)
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS mooring_stations (
            station_id INTEGER PRIMARY KEY AUTOINCREMENT,
            station_name TEXT UNIQUE NOT NULL,
            x_m REAL,
            y_m REAL,
            z_m REAL,
            side TEXT,
            notes TEXT,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bollards (
            bollard_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bollard_name TEXT UNIQUE NOT NULL,
            station_name TEXT,
            x_m REAL,
            y_m REAL,
            z_m REAL,
            swl_kn REAL,
            notes TEXT,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS ports (
            port_name TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            berth_heading REAL,
            updated_at TEXT NOT NULL
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_history (
            analysis_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            port_name TEXT,
            wind_speed_kn REAL,
            wind_direction_deg REAL,
            current_speed_kn REAL,
            current_direction_deg REAL,
            result_json TEXT
        )
        """)

        now = utc_now()

        for port_name, coords in PORT_COORDINATES.items():

            conn.execute("""
            INSERT INTO ports
            (
                port_name,
                latitude,
                longitude,
                berth_heading,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(port_name)
            DO NOTHING
            """, (
                port_name,
                coords["lat"],
                coords["lon"],
                DEFAULT_PORT_HEADINGS.get(port_name, 0.0),
                now,
            ))


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def backup_database():

    if not os.path.exists(DB_FILE):
        return None

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = os.path.join(
        BACKUP_DIR,
        f"openmooring_backup_{timestamp}.db"
    )

    shutil.copy2(DB_FILE, destination)

    return destination


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def query_df(query, params=()):

    with get_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_certificates():

    return query_df("""
        SELECT *
        FROM certificates
        ORDER BY updated_at DESC
    """)


def get_lines():

    return query_df("""
        SELECT *
        FROM mooring_lines
        ORDER BY line_name
    """)


def get_stations():

    return query_df("""
        SELECT *
        FROM mooring_stations
        ORDER BY station_name
    """)


def get_bollards():

    return query_df("""
        SELECT *
        FROM bollards
        ORDER BY bollard_name
    """)


def get_ports():

    return query_df("""
        SELECT *
        FROM ports
        ORDER BY port_name
    """)


def upsert_certificate(data):

    now = utc_now()

    with get_connection() as conn:

        conn.execute("""
        INSERT INTO certificates
        (
            cert_id,
            manufacturer,
            material,
            diameter_mm,
            mbl_kn,
            mbl_tons,
            standard,
            issue_date,
            expiry_date,
            source_text,
            created_at,
            updated_at
        )
        VALUES
        (
            :cert_id,
            :manufacturer,
            :material,
            :diameter_mm,
            :mbl_kn,
            :mbl_tons,
            :standard,
            :issue_date,
            :expiry_date,
            :source_text,
            :created_at,
            :updated_at
        )
        ON CONFLICT(cert_id)
        DO UPDATE SET

            manufacturer=excluded.manufacturer,
            material=excluded.material,
            diameter_mm=excluded.diameter_mm,
            mbl_kn=excluded.mbl_kn,
            mbl_tons=excluded.mbl_tons,
            standard=excluded.standard,
            issue_date=excluded.issue_date,
            expiry_date=excluded.expiry_date,
            source_text=excluded.source_text,
            updated_at=excluded.updated_at
        """, {
            **data,
            "created_at": now,
            "updated_at": now,
        })


def upsert_line(data):

    now = utc_now()

    with get_connection() as conn:

        conn.execute("""
        INSERT INTO mooring_lines
        (
            line_name,
            station,
            line_type,
            material,
            diameter_mm,
            length_m,
            mbl_kn,
            mbl_tons,
            cert_id,
            brake_holding_capacity_kn,
            condition,
            notes,
            updated_at
        )
        VALUES
        (
            :line_name,
            :station,
            :line_type,
            :material,
            :diameter_mm,
            :length_m,
            :mbl_kn,
            :mbl_tons,
            :cert_id,
            :brake_holding_capacity_kn,
            :condition,
            :notes,
            :updated_at
        )
        ON CONFLICT(line_name)
        DO UPDATE SET

            station=excluded.station,
            line_type=excluded.line_type,
            material=excluded.material,
            diameter_mm=excluded.diameter_mm,
            length_m=excluded.length_m,
            mbl_kn=excluded.mbl_kn,
            mbl_tons=excluded.mbl_tons,
            cert_id=excluded.cert_id,
            brake_holding_capacity_kn=excluded.brake_holding_capacity_kn,
            condition=excluded.condition,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """, {
            **data,
            "updated_at": now,
        })


def update_line_certificate(line_name, cert):

    with get_connection() as conn:

        conn.execute("""
        UPDATE mooring_lines

        SET
            cert_id=?,
            material=?,
            diameter_mm=?,
            mbl_kn=?,
            mbl_tons=?,
            updated_at=?

        WHERE line_name=?
        """, (
            cert["cert_id"],
            cert["material"],
            cert["diameter_mm"],
            cert["mbl_kn"],
            cert["mbl_tons"],
            utc_now(),
            line_name,
        ))


def upsert_station(data):

    with get_connection() as conn:

        conn.execute("""
        INSERT INTO mooring_stations
        (
            station_name,
            x_m,
            y_m,
            z_m,
            side,
            notes,
            updated_at
        )
        VALUES
        (
            :station_name,
            :x_m,
            :y_m,
            :z_m,
            :side,
            :notes,
            :updated_at
        )
        ON CONFLICT(station_name)
        DO UPDATE SET

            x_m=excluded.x_m,
            y_m=excluded.y_m,
            z_m=excluded.z_m,
            side=excluded.side,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """, {
            **data,
            "updated_at": utc_now(),
        })


def upsert_bollard(data):

    with get_connection() as conn:

        conn.execute("""
        INSERT INTO bollards
        (
            bollard_name,
            station_name,
            x_m,
            y_m,
            z_m,
            swl_kn,
            notes,
            updated_at
        )
        VALUES
        (
            :bollard_name,
            :station_name,
            :x_m,
            :y_m,
            :z_m,
            :swl_kn,
            :notes,
            :updated_at
        )
        ON CONFLICT(bollard_name)
        DO UPDATE SET

            station_name=excluded.station_name,
            x_m=excluded.x_m,
            y_m=excluded.y_m,
            z_m=excluded.z_m,
            swl_kn=excluded.swl_kn,
            notes=excluded.notes,
            updated_at=excluded.updated_at
        """, {
            **data,
            "updated_at": utc_now(),
        })


# =============================================================================
# UNIT CONVERSION
# =============================================================================

def normalize_number(value):

    if value is None:
        return None

    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def force_to_kn(value, unit):

    value = normalize_number(value)

    if value is None:
        return None

    unit = (unit or "").lower().strip()

    if unit in ["kn", "kilonewton", "kilonewtons"]:
        return value

    if unit in ["t", "ton", "tons", "tonne", "tonnes", "tf"]:
        return value * TON_FORCE_TO_KN

    if unit in ["kgf", "kg"]:
        return value * KGF_TO_KN

    if unit in ["lbf", "lb", "lbs"]:
        return value * LBF_TO_KN

    return None


def length_to_mm(value, unit):

    value = normalize_number(value)

    if value is None:
        return None

    unit = (unit or "").lower().strip()

    if unit in ["mm", "millimeter", "millimeters"]:
        return value

    if unit in ["cm", "centimeter", "centimeters"]:
        return value * 10

    if unit in ["m", "meter", "meters", "metre", "metres"]:
        return value * 1000

    if unit in ["in", "inch", "inches", '"']:
        return value * 25.4

    return None


def kn_to_tonnes(kn):

    if kn is None:
        return None

    return kn / TON_FORCE_TO_KN


# =============================================================================
# CERTIFICATE PARSER
# =============================================================================

MATERIAL_PATTERNS = {

    "HMPE": [
        "HMPE",
        "UHMWPE",
        "ULTRA HIGH MOLECULAR WEIGHT POLYETHYLENE",
        "HIGH MODULUS POLYETHYLENE",
    ],

    "DYNEEMA": [
        "DYNEEMA",
    ],

    "POLYESTER": [
        "POLYESTER",
        "PET",
    ],

    "NYLON": [
        "NYLON",
        "POLYAMIDE",
        "PA6",
        "PA 6",
    ],

    "ARAMID": [
        "ARAMID",
        "KEVLAR",
        "TECHNORA",
    ],

    "POLYPROPYLENE": [
        "POLYPROPYLENE",
        "PP",
    ],

    "WIRE": [
        "WIRE ROPE",
        "STEEL WIRE",
        "GALVANIZED WIRE",
    ],
}


def extract_first_match(patterns, text, flags=re.IGNORECASE):

    for pattern in patterns:

        match = re.search(pattern, text, flags)

        if match:
            return match

    return None


def normalize_material(text):

    if not text:
        return None

    upper_text = text.upper()

    for canonical, aliases in MATERIAL_PATTERNS.items():

        for alias in aliases:

            if alias in upper_text:
                return canonical

    return None


def extract_certificate_id(text):

    patterns = [

        r"(?:CERTIFICATE\s*(?:NO|NUMBER|#)?|CERT\.?\s*NO|CERT\s*NO)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-_\/\.]{3,})",

        r"(?:CERTIFICATE)\s+([A-Z0-9][A-Z0-9\-_\/\.]{3,})",

        r"(?:SERIAL\s*(?:NO|NUMBER)?|S\/N)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-_\/\.]{3,})",
    ]

    match = extract_first_match(patterns, text)

    return match.group(1).strip() if match else None


def extract_manufacturer(text):

    patterns = [

        r"(?:MANUFACTURER|MANUFACTURED BY|MAKER|PRODUCER)\s*[:\-]?\s*([A-Z0-9&.,() \-]{3,60})",

        r"(?:MANUFACTURER)\s*\n?\s*([A-Z0-9&.,() \-]{3,60})",
    ]

    match = extract_first_match(patterns, text)

    if match:

        result = match.group(1).strip()

        result = re.split(
            r"\n|CERTIFICATE|DATE|MATERIAL|DIAMETER",
            result,
            flags=re.IGNORECASE
        )[0].strip()

        return result or None

    return None


def extract_diameter_mm(text):

    patterns = [

        r"(?:DIAMETER|DIAM\.?|Ø)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*(MM|CM|M|IN|INCH|INCHES)?",

        r"(\d+(?:[.,]\d+)?)\s*(MM|CM|IN|INCH|INCHES)\s*(?:DIAMETER|ROPE)",
    ]

    match = extract_first_match(patterns, text)

    if not match:
        return None

    value = match.group(1)
    unit = match.group(2) or "mm"

    return length_to_mm(value, unit)


def extract_mbl_kn(text):

    patterns = [

        r"(?:MBL|MINIMUM BREAKING LOAD|BREAKING LOAD|MIN\.?\s*BREAKING\s*STRENGTH|MBS)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)\s*(KN|KILONEWTONS?|TONNES?|TONS?|T|TF|KGF|LBF)?",

        r"(\d+(?:[.,]\d+)?)\s*(KN|KILONEWTONS?|TONNES?|TONS?|T|TF|KGF|LBF)\s*(?:MBL|BREAKING LOAD|MBS)",
    ]

    match = extract_first_match(patterns, text)

    if not match:
        return None

    value = match.group(1)
    unit = match.group(2)

    if not unit:
        return None

    return force_to_kn(value, unit)


def extract_standard(text):

    standards = [

        "MEG4",
        "MEG 4",
        "OCIMF",
        "ISO 2307",
        "ISO 9554",
        "EN ISO",
        "ABS",
        "DNV",
        "LLOYD'S REGISTER",
        "LR",
        "BV",
        "BUREAU VERITAS",
    ]

    upper = text.upper()

    for standard in standards:

        if standard.upper() in upper:
            return standard

    return None


def extract_dates(text):

    date_patterns = [

        r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b",

        r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b",

        r"\b(\d{2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\s+\d{4})\b",
    ]

    dates = []

    for pattern in date_patterns:

        dates.extend(
            re.findall(pattern, text, re.IGNORECASE)
        )

    return list(dict.fromkeys(dates))


def parse_certificate_text(text):

    if not text:
        return {}

    text = re.sub(r"\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    mbl_kn = extract_mbl_kn(text)

    return {

        "cert_id": extract_certificate_id(text),

        "manufacturer": extract_manufacturer(text),

        "material": normalize_material(text),

        "diameter_mm": extract_diameter_mm(text),

        "mbl_kn": mbl_kn,

        "mbl_tons": kn_to_tonnes(mbl_kn),

        "standard": extract_standard(text),

        "dates_found": extract_dates(text),

        "source_text": text,
    }


def extract_pdf_text(uploaded_file):

    if uploaded_file is None:
        return ""

    text = ""

    if pdfplumber:

        try:

            with pdfplumber.open(uploaded_file) as pdf:

                for page in pdf.pages:

                    page_text = page.extract_text() or ""

                    text += page_text + "\n"

            if text.strip():
                return text

        except Exception:
            pass

    if PdfReader:

        try:

            uploaded_file.seek(0)

            reader = PdfReader(uploaded_file)

            for page in reader.pages:

                text += (page.extract_text() or "") + "\n"

        except Exception:
            pass

    return text


# =============================================================================
# WEATHER
# =============================================================================

@st.cache_data(ttl=600)
def fetch_live_weather(latitude, longitude):

    try:

        url = "https://api.open-meteo.com/v1/forecast"

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "kn",
            "timezone": "UTC",
        }

        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

        current = data.get("current", {})

        speed = current.get("wind_speed_10m")
        direction = current.get("wind_direction_10m")
        timestamp = current.get("time")

        if speed is None or direction is None:
            return False, None, None, None

        return (
            True,
            float(speed),
            float(direction),
            timestamp,
        )

    except Exception:

        return False, None, None, None


# =============================================================================
# MOORING CALCULATIONS
# =============================================================================

def angle_to_vector(angle_deg):

    angle_rad = math.radians(angle_deg)

    return np.array([
        math.cos(angle_rad),
        math.sin(angle_rad),
    ], dtype=float)


def calculate_environmental_force(
    wind_speed_kn,
    wind_direction_deg,
    current_speed_kn,
    current_direction_deg,
    projected_wind_area_m2=0.0,
    projected_current_area_m2=0.0,
    air_drag_coefficient=1.0,
    water_drag_coefficient=1.0,
):

    wind_speed_mps = wind_speed_kn * KNOT_TO_MPS
    current_speed_mps = current_speed_kn * KNOT_TO_MPS

    rho_air = 1.225
    rho_water = 1025.0

    wind_force_n = (
        0.5
        * rho_air
        * air_drag_coefficient
        * projected_wind_area_m2
        * wind_speed_mps ** 2
    )

    current_force_n = (
        0.5
        * rho_water
        * water_drag_coefficient
        * projected_current_area_m2
        * current_speed_mps ** 2
    )

    wind_force_kn = wind_force_n / 1000.0
    current_force_kn = current_force_n / 1000.0

    wind_vector = (
        angle_to_vector(wind_direction_deg)
        * wind_force_kn
    )

    current_vector = (
        angle_to_vector(current_direction_deg)
        * current_force_kn
    )

    total_vector = wind_vector + current_vector

    return {
        "wind_force_kn": wind_force_kn,
        "current_force_kn": current_force_kn,
        "wind_vector": wind_vector,
        "current_vector": current_vector,
        "total_vector": total_vector,
        "total_force_kn": float(
            np.linalg.norm(total_vector)
        ),
    }


def calculate_line_geometry(
    line_start,
    line_end,
):

    start = np.array(line_start, dtype=float)
    end = np.array(line_end, dtype=float)

    vector = end - start

    horizontal_vector = vector[:2]

    horizontal_distance = np.linalg.norm(horizontal_vector)

    total_distance = np.linalg.norm(vector)

    if total_distance <= 0:

        return {
            "valid": False,
            "reason": "La lunghezza geometrica della linea è zero.",
        }

    unit_3d = vector / total_distance

    if horizontal_distance <= 0:

        horizontal_unit = np.array([0.0, 0.0])

    else:

        horizontal_unit = (
            horizontal_vector
            / horizontal_distance
        )

    horizontal_angle = (
        math.degrees(
            math.atan2(
                horizontal_unit[1],
                horizontal_unit[0],
            )
        )
        % 360
    )

    vertical_angle = math.degrees(
        math.atan2(
            vector[2],
            horizontal_distance,
        )
    )

    return {
        "valid": True,
        "vector": vector,
        "unit_3d": unit_3d,
        "unit_horizontal": horizontal_unit,
        "horizontal_distance_m": float(
            horizontal_distance
        ),
        "distance_m": float(total_distance),
        "horizontal_angle_deg": float(
            horizontal_angle
        ),
        "vertical_angle_deg": float(
            vertical_angle
        ),
    }


def solve_line_tensions(
    line_vectors,
    external_force_kn,
    regularization=1e-8,
):

    if len(line_vectors) == 0:

        return {
            "success": False,
            "reason": "Nessuna linea disponibile.",
        }

    A = np.array(
        line_vectors,
        dtype=float,
    ).T

    b = -np.array(
        external_force_kn,
        dtype=float,
    )

    if A.shape[0] != 2:

        return {
            "success": False,
            "reason": "La matrice delle forze deve avere 2 componenti.",
        }

    rank = np.linalg.matrix_rank(A)

    try:

        condition_number = np.linalg.cond(A)

    except Exception:

        condition_number = float("inf")

    method = "least_squares"

    try:

        if (
            A.shape[0] == A.shape[1]
            and rank == min(A.shape)
            and np.isfinite(condition_number)
            and condition_number < 1e8
        ):

            tensions = np.linalg.solve(A, b)

            method = "direct"

        else:

            ATA = A.T @ A
            ATb = A.T @ b

            if regularization > 0:

                ATA = (
                    ATA
                    + regularization
                    * np.eye(ATA.shape[0])
                )

            tensions = np.linalg.lstsq(
                ATA,
                ATb,
                rcond=None,
            )[0]

    except Exception as exc:

        return {
            "success": False,
            "reason": str(exc),
        }

    residual = A @ tensions - b

    return {
        "success": True,
        "tensions_kn": tensions,
        "residual_kn": residual,
        "residual_norm_kn": float(
            np.linalg.norm(residual)
        ),
        "matrix_rank": int(rank),
        "condition_number": float(
            condition_number
        ),
        "method": method,
    }


# =============================================================================
# VISUALIZATION
# =============================================================================

def create_force_plot(result):

    fig = go.Figure()

    total = result["total_vector"]
    wind = result["wind_vector"]
    current = result["current_vector"]

    vectors = [
        ("Wind", wind),
        ("Current", current),
        ("Total", total),
    ]

    for name, vector in vectors:

        fig.add_trace(
            go.Scatter(
                x=[0, vector[0]],
                y=[0, vector[1]],
                mode="lines+markers",
                name=name,
            )
        )

    fig.update_layout(
        title="Environmental Force Vectors",
        xaxis_title="Longitudinal Force [kN]",
        yaxis_title="Transverse Force [kN]",
        height=500,
        showlegend=True,
    )

    fig.update_yaxes(
        scaleanchor="x",
        scaleratio=1,
    )

    return fig


# =============================================================================
# INITIALIZATION
# =============================================================================

init_db()


# =============================================================================
# SIDEBAR
# =============================================================================

st.sidebar.title("⚓ OpenMooring")

st.sidebar.divider()

ports_df = get_ports()

port_names = ports_df["port_name"].tolist()

selected_port = st.sidebar.selectbox(
    "📍 Porto di riferimento",
    port_names,
)

selected_port_row = ports_df[
    ports_df["port_name"] == selected_port
].iloc[0]

berth_heading = float(
    selected_port_row["berth_heading"]
    if pd.notna(selected_port_row["berth_heading"])
    else 0.0
)

meteo_mode = st.sidebar.radio(
    "Condizioni meteo",
    [
        "Manuale",
        "Live Open-Meteo",
    ],
)

if meteo_mode == "Live Open-Meteo":

    if st.sidebar.button("🔄 Aggiorna meteo live"):

        st.cache_data.clear()

    success, live_speed, live_direction, weather_time = (
        fetch_live_weather(
            selected_port_row["latitude"],
            selected_port_row["longitude"],
        )
    )

    if success:

        relative_direction = (
            live_direction - berth_heading
        ) % 360

        st.sidebar.success(
            f"{live_speed:.1f} kn @ "
            f"{live_direction:.0f}° True"
        )

        st.sidebar.caption(
            f"Data source time: {weather_time} UTC"
        )

        v_wind = live_speed
        dir_wind = relative_direction

    else:

        st.sidebar.warning(
            "Dati live non disponibili. "
            "Inserire valori manuali."
        )

        v_wind = st.sidebar.number_input(
            "Vento [kn]",
            min_value=0.0,
            value=0.0,
        )

        dir_wind = st.sidebar.number_input(
            "Direzione relativa [°]",
            min_value=0.0,
            max_value=360.0,
            value=0.0,
        )

else:

    v_wind = st.sidebar.number_input(
        "Vento [kn]",
        min_value=0.0,
        value=0.0,
    )

    dir_wind = st.sidebar.number_input(
        "Direzione vento relativa [°]",
        min_value=0.0,
        max_value=360.0,
        value=0.0,
    )


v_curr = st.sidebar.number_input(
    "Corrente [kn]",
    min_value=0.0,
    value=0.0,
)

dir_curr = st.sidebar.number_input(
    "Direzione corrente [°]",
    min_value=0.0,
    max_value=360.0,
    value=0.0,
)

st.sidebar.divider()

if st.sidebar.button("💾 Backup Database"):

    backup_file = backup_database()

    if backup_file:

        st.sidebar.success(
            f"Backup creato: {backup_file}"
        )

    else:

        st.sidebar.warning(
            "Database non ancora disponibile."
        )


# =============================================================================
# MAIN UI
# =============================================================================

st.title(APP_TITLE)
st.caption(
    "Persistent Mooring Analysis, Certificate Management "
    "and Environmental Load Calculation"
)

tabs = st.tabs([
    "🏠 Dashboard",
    "📜 Certificates",
    "🪢 Mooring Lines",
    "🏗️ Stations & Bollards",
    "🌊 Analysis",
])


# =============================================================================
# DASHBOARD
# =============================================================================

with tabs[0]:

    st.header("🏠 Home Dashboard")

    certificates_df = get_certificates()
    lines_df = get_lines()
    stations_df = get_stations()
    bollards_df = get_bollards()

    total_lines = len(lines_df)

    total_certificates = len(certificates_df)

    total_stations = len(stations_df)

    total_bollards = len(bollards_df)

    missing_certificate = 0

    if not lines_df.empty:

        missing_certificate = int(
            lines_df["cert_id"]
            .isna()
            .sum()
        )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Mooring Lines",
        total_lines,
    )

    col2.metric(
        "Certificates",
        total_certificates,
    )

    col3.metric(
        "Stations",
        total_stations,
    )

    col4.metric(
        "Bollards",
        total_bollards,
    )

    st.divider()

    st.subheader("⚠️ Data Quality Alerts")

    alerts = []

    if total_lines == 0:

        alerts.append(
            "No mooring lines are currently registered."
        )

    if missing_certificate > 0:

        alerts.append(
            f"{missing_certificate} line(s) do not have an associated certificate."
        )

    if not lines_df.empty:

        missing_mbl = lines_df["mbl_kn"].isna().sum()

        if missing_mbl > 0:

            alerts.append(
                f"{missing_mbl} line(s) do not have a verified MBL."
            )

        missing_brake = (
            lines_df["brake_holding_capacity_kn"]
            .isna()
            .sum()
        )

        if missing_brake > 0:

            alerts.append(
                f"{missing_brake} line(s) do not have Brake Holding Capacity data."
            )

    if alerts:

        for alert in alerts:
            st.warning(alert)

    else:

        st.success(
            "No critical data completeness alerts detected."
        )

    st.divider()

    st.subheader("Current Inventory")

    if not lines_df.empty:

        display_columns = [
            col for col in [
                "line_name",
                "station",
                "line_type",
                "material",
                "diameter_mm",
                "mbl_kn",
                "cert_id",
                "condition",
            ]
            if col in lines_df.columns
        ]

        st.dataframe(
            lines_df[display_columns],
            use_container_width=True,
        )

    else:

        st.info(
            "Add mooring lines from the Mooring Lines tab."
        )


# =============================================================================
# CERTIFICATES
# =============================================================================

with tabs[1]:

    st.header("📜 Certificate Management")

    col1, col2 = st.columns(2)

    with col1:

        st.subheader("Upload Certificate")

        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"],
        )

        manual_text = st.text_area(
            "Or paste certificate text",
            height=250,
        )

        certificate_text = ""

        if uploaded_file is not None:

            certificate_text = extract_pdf_text(
                uploaded_file
            )

        if manual_text.strip():

            certificate_text = manual_text

        if st.button(
            "🔍 Parse Certificate",
            key="parse_certificate"
        ):

            if not certificate_text.strip():

                st.error(
                    "No certificate text available."
                )

            else:

                parsed = parse_certificate_text(
                    certificate_text
                )

                st.session_state[
                    "parsed_certificate"
                ] = parsed

                st.success(
                    "Certificate parsing completed."
                )

    with col2:

        st.subheader("Parsed Data")

        parsed = st.session_state.get(
            "parsed_certificate",
            {}
        )

        if parsed:

            cert_id = st.text_input(
                "Certificate ID",
                value=parsed.get("cert_id") or "",
            )

            manufacturer = st.text_input(
                "Manufacturer",
                value=parsed.get("manufacturer") or "",
            )

            material = st.text_input(
                "Material",
                value=parsed.get("material") or "",
            )

            diameter = st.number_input(
                "Diameter [mm]",
                min_value=0.0,
                value=float(
                    parsed.get("diameter_mm") or 0.0
                ),
            )

            mbl_kn = st.number_input(
                "MBL [kN]",
                min_value=0.0,
                value=float(
                    parsed.get("mbl_kn") or 0.0
                ),
            )

            standard = st.text_input(
                "Standard",
                value=parsed.get("standard") or "",
            )

            issue_date = st.text_input(
                "Issue Date",
                value="",
            )

            expiry_date = st.text_input(
                "Expiry Date",
                value="",
            )

            if st.button(
                "💾 Save Certificate"
            ):

                if not cert_id.strip():

                    st.error(
                        "Certificate ID is required."
                    )

                else:

                    verified_mbl_kn = (
                        mbl_kn
                        if mbl_kn > 0
                        else None
                    )

                    verified_diameter = (
                        diameter
                        if diameter > 0
                        else None
                    )

                    upsert_certificate({

                        "cert_id": cert_id.strip(),

                        "manufacturer": (
                            manufacturer.strip()
                            or None
                        ),

                        "material": (
                            material.strip()
                            or None
                        ),

                        "diameter_mm": verified_diameter,

                        "mbl_kn": verified_mbl_kn,

                        "mbl_tons": (
                            kn_to_tonnes(
                                verified_mbl_kn
                            )
                            if verified_mbl_kn
                            else None
                        ),

                        "standard": (
                            standard.strip()
                            or None
                        ),

                        "issue_date": (
                            issue_date.strip()
                            or None
                        ),

                        "expiry_date": (
                            expiry_date.strip()
                            or None
                        ),

                        "source_text": (
                            parsed.get(
                                "source_text",
                                ""
                            )
                        ),
                    })

                    st.success(
                        f"Certificate {cert_id} saved."
                    )

                    st.rerun()

        else:

            st.info(
                "Upload or paste a certificate and run the parser."
            )

    st.divider()

    st.subheader("Registered Certificates")

    certificates_df = get_certificates()

    st.dataframe(
        certificates_df,
        use_container_width=True,
    )


# =============================================================================
# MOORING LINES
# =============================================================================

with tabs[2]:

    st.header("🪢 Mooring Line Inventory")

    certificates_df = get_certificates()

    with st.expander(
        "➕ Add / Update Mooring Line",
        expanded=False,
    ):

        with st.form("line_form"):

            line_name = st.text_input(
                "Line Name"
            )

            station = st.text_input(
                "Station"
            )

            line_type = st.selectbox(
                "Line Type",
                [
                    "",
                    "Head Line",
                    "Stern Line",
                    "Breast Line",
                    "Spring Line",
                    "Other",
                ],
            )

            material = st.text_input(
                "Material"
            )

            diameter_mm = st.number_input(
                "Diameter [mm]",
                min_value=0.0,
            )

            length_m = st.number_input(
                "Length [m]",
                min_value=0.0,
            )

            mbl_kn = st.number_input(
                "MBL [kN]",
                min_value=0.0,
            )

            brake_holding_capacity_kn = (
                st.number_input(
                    "Brake Holding Capacity [kN]",
                    min_value=0.0,
                    help=(
                        "Leave at zero if the verified "
                        "value is not currently available."
                    ),
                )
            )

            condition = st.selectbox(
                "Condition",
                [
                    "Unknown",
                    "Good",
                    "Fair",
                    "Monitor",
                    "Replace",
                ],
            )

            notes = st.text_area(
                "Notes"
            )

            submitted = st.form_submit_button(
                "💾 Save Line"
            )

        if submitted:

            if not line_name.strip():

                st.error(
                    "Line Name is required."
                )

            else:

                verified_mbl = (
                    mbl_kn
                    if mbl_kn > 0
                    else None
                )

                verified_brake = (
                    brake_holding_capacity_kn
                    if brake_holding_capacity_kn > 0
                    else None
                )

                upsert_line({

                    "line_name": line_name.strip(),

                    "station": (
                        station.strip()
                        or None
                    ),

                    "line_type": (
                        line_type
                        or None
                    ),

                    "material": (
                        material.strip()
                        or None
                    ),

                    "diameter_mm": (
                        diameter_mm
                        if diameter_mm > 0
                        else None
                    ),

                    "length_m": (
                        length_m
                        if length_m > 0
                        else None
                    ),

                    "mbl_kn": verified_mbl,

                    "mbl_tons": (
                        kn_to_tonnes(
                            verified_mbl
                        )
                        if verified_mbl
                        else None
                    ),

                    "cert_id": None,

                    "brake_holding_capacity_kn": (
                        verified_brake
                    ),

                    "condition": condition,

                    "notes": (
                        notes.strip()
                        or None
                    ),
                })

                st.success(
                    f"Line {line_name} saved."
                )

                st.rerun()

    lines_df = get_lines()

    if not lines_df.empty:

        st.subheader(
            "Associate Certificate"
        )

        col1, col2 = st.columns(2)

        selected_line = col1.selectbox(
            "Select Line",
            lines_df["line_name"].tolist(),
        )

        if not certificates_df.empty:

            selected_cert = col2.selectbox(
                "Select Certificate",
                certificates_df["cert_id"].tolist(),
            )

            if st.button(
                "🔗 Apply Certificate"
            ):

                cert = certificates_df[
                    certificates_df["cert_id"]
                    == selected_cert
                ].iloc[0]

                update_line_certificate(
                    selected_line,
                    cert,
                )

                st.success(
                    "Certificate applied to line."
                )

                st.rerun()

        else:

            st.info(
                "No certificates available."
            )

    st.divider()

    lines_df = get_lines()

    st.dataframe(
        lines_df,
        use_container_width=True,
    )


# =============================================================================
# STATIONS AND BOLLARDS
# =============================================================================

with tabs[3]:

    st.header("🏗️ Mooring Stations & Bollards")

    col_station, col_bollard = st.columns(2)

    with col_station:

        st.subheader("Mooring Station")

        with st.form("station_form"):

            station_name = st.text_input(
                "Station Name"
            )

            x_m = st.number_input(
                "X [m]",
                value=0.0,
            )

            y_m = st.number_input(
                "Y [m]",
                value=0.0,
            )

            z_m = st.number_input(
                "Z [m]",
                value=0.0,
            )

            side = st.selectbox(
                "Side",
                [
                    "",
                    "Port",
                    "Starboard",
                    "Center",
                ],
            )

            notes = st.text_area(
                "Station Notes"
            )

            if st.form_submit_button(
                "Save Station"
            ):

                if station_name.strip():

                    upsert_station({

                        "station_name": (
                            station_name.strip()
                        ),

                        "x_m": x_m,

                        "y_m": y_m,

                        "z_m": z_m,

                        "side": side or None,

                        "notes": (
                            notes.strip()
                            or None
                        ),
                    })

                    st.success(
                        "Station saved."
                    )

                    st.rerun()

                else:

                    st.error(
                        "Station name is required."
                    )

    with col_bollard:

        st.subheader("Bollard")

        with st.form("bollard_form"):

            bollard_name = st.text_input(
                "Bollard Name"
            )

            station_name = st.text_input(
                "Associated Station"
            )

            x_m = st.number_input(
                "Bollard X [m]",
                value=0.0,
            )

            y_m = st.number_input(
                "Bollard Y [m]",
                value=0.0,
            )

            z_m = st.number_input(
                "Bollard Z [m]",
                value=0.0,
            )

            swl_kn = st.number_input(
                "SWL [kN]",
                min_value=0.0,
            )

            notes = st.text_area(
                "Bollard Notes"
            )

            if st.form_submit_button(
                "Save Bollard"
            ):

                if bollard_name.strip():

                    upsert_bollard({

                        "bollard_name": (
                            bollard_name.strip()
                        ),

                        "station_name": (
                            station_name.strip()
                            or None
                        ),

                        "x_m": x_m,

                        "y_m": y_m,

                        "z_m": z_m,

                        "swl_kn": (
                            swl_kn
                            if swl_kn > 0
                            else None
                        ),

                        "notes": (
                            notes.strip()
                            or None
                        ),
                    })

                    st.success(
                        "Bollard saved."
                    )

                    st.rerun()

                else:

                    st.error(
                        "Bollard name is required."
                    )

    st.divider()

    col1, col2 = st.columns(2)

    with col1:

        st.subheader("Stations")

        st.dataframe(
            get_stations(),
            use_container_width=True,
        )

    with col2:

        st.subheader("Bollards")

        st.dataframe(
            get_bollards(),
            use_container_width=True,
        )


# =============================================================================
# ANALYSIS
# =============================================================================

with tabs[4]:

    st.header("🌊 Mooring Analysis")

    st.subheader(
        "Environmental Input"
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        projected_wind_area = st.number_input(
            "Projected Wind Area [m²]",
            min_value=0.0,
            value=0.0,
        )

        air_drag_coefficient = st.number_input(
            "Air Drag Coefficient",
            min_value=0.0,
            value=1.0,
        )

    with col2:

        projected_current_area = st.number_input(
            "Projected Current Area [m²]",
            min_value=0.0,
            value=0.0,
        )

        water_drag_coefficient = st.number_input(
            "Water Drag Coefficient",
            min_value=0.0,
            value=1.0,
        )

    with col3:

        st.metric(
            "Wind",
            f"{v_wind:.1f} kn",
        )

        st.metric(
            "Current",
            f"{v_curr:.1f} kn",
        )

        st.metric(
            "Port",
            selected_port,
        )

    result = calculate_environmental_force(

        wind_speed_kn=v_wind,

        wind_direction_deg=dir_wind,

        current_speed_kn=v_curr,

        current_direction_deg=dir_curr,

        projected_wind_area_m2=(
            projected_wind_area
        ),

        projected_current_area_m2=(
            projected_current_area
        ),

        air_drag_coefficient=(
            air_drag_coefficient
        ),

        water_drag_coefficient=(
            water_drag_coefficient
        ),
    )

    st.divider()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Wind Force",
        f"{result['wind_force_kn']:.2f} kN",
    )

    c2.metric(
        "Current Force",
        f"{result['current_force_kn']:.2f} kN",
    )

    c3.metric(
        "Resultant Force",
        f"{result['total_force_kn']:.2f} kN",
    )

    st.plotly_chart(
        create_force_plot(result),
        use_container_width=True,
    )

    st.divider()

    st.subheader(
        "Mooring Line Equilibrium"
    )

    lines_df = get_lines()

    if lines_df.empty:

        st.info(
            "No mooring lines available for analysis."
        )

    else:

        available_lines = (
            lines_df["line_name"]
            .tolist()
        )

        selected_lines = st.multiselect(
            "Select lines for calculation",
            available_lines,
            default=available_lines,
        )

        geometry_data = []

        for line_name in selected_lines:

            with st.expander(
                f"Geometry: {line_name}"
            ):

                c1, c2, c3, c4 = st.columns(4)

                start_x = c1.number_input(
                    "Ship X [m]",
                    value=0.0,
                    key=f"{line_name}_sx",
                )

                start_y = c2.number_input(
                    "Ship Y [m]",
                    value=0.0,
                    key=f"{line_name}_sy",
                )

                end_x = c3.number_input(
                    "Shore X [m]",
                    value=0.0,
                    key=f"{line_name}_ex",
                )

                end_y = c4.number_input(
                    "Shore Y [m]",
                    value=0.0,
                    key=f"{line_name}_ey",
                )

                geometry = calculate_line_geometry(

                    [start_x, start_y, 0.0],

                    [end_x, end_y, 0.0],
                )

                if geometry["valid"]:

                    st.caption(
                        f"Angle: "
                        f"{geometry['horizontal_angle_deg']:.1f}° | "
                        f"Distance: "
                        f"{geometry['distance_m']:.2f} m"
                    )

                    geometry_data.append({

                        "line_name": line_name,

                        "vector": (
                            geometry[
                                "unit_horizontal"
                            ]
                        ),
                    })

                else:

                    st.error(
                        geometry["reason"]
                    )

        if (
            st.button(
                "⚙️ Calculate Line Equilibrium"
            )
            and geometry_data
        ):

            vectors = [
                item["vector"]
                for item in geometry_data
            ]

            external_force = (
                result["total_vector"]
            )

            solution = solve_line_tensions(
                vectors,
                external_force,
            )

            if solution["success"]:

                tension_values = (
                    solution["tensions_kn"]
                )

                output = []

                for i, item in enumerate(
                    geometry_data
                ):

                    line_row = lines_df[
                        lines_df["line_name"]
                        == item["line_name"]
                    ].iloc[0]

                    calculated_tension = float(
                        tension_values[i]
                    )

                    mbl_kn = line_row["mbl_kn"]

                    utilization = None

                    if (
                        pd.notna(mbl_kn)
                        and mbl_kn > 0
                    ):

                        utilization = (
                            abs(calculated_tension)
                            / mbl_kn
                            * 100
                        )

                    output.append({

                        "Line": item[
                            "line_name"
                        ],

                        "Calculated Tension [kN]": (
                            calculated_tension
                        ),

                        "MBL [kN]": (
                            mbl_kn
                            if pd.notna(mbl_kn)
                            else None
                        ),

                        "Utilization [%]": (
                            utilization
                        ),

                        "Brake Holding Capacity [kN]": (
                            line_row[
                                "brake_holding_capacity_kn"
                            ]
                            if pd.notna(
                                line_row[
                                    "brake_holding_capacity_kn"
                                ]
                            )
                            else None
                        ),
                    })

                output_df = pd.DataFrame(
                    output
                )

                st.success(
                    f"Calculation completed using "
                    f"{solution['method']}."
                )

                st.dataframe(
                    output_df,
                    use_container_width=True,
                )

                st.caption(
                    f"Matrix rank: "
                    f"{solution['matrix_rank']} | "
                    f"Condition number: "
                    f"{solution['condition_number']:.2e} | "
                    f"Residual: "
                    f"{solution['residual_norm_kn']:.6f} kN"
                )

                high_utilization = output_df[
                    output_df["Utilization [%]"] > 100
                ]

                if not high_utilization.empty:

                    st.error(
                        "One or more lines exceed 100% of the stored MBL."
                    )

                elif output_df[
                    "Utilization [%]"
                ].notna().any():

                    st.success(
                        "No calculated line utilization exceeds 100% of stored MBL."
                    )

                with get_connection() as conn:

                    conn.execute("""
                    INSERT INTO analysis_history
                    (
                        timestamp,
                        port_name,
                        wind_speed_kn,
                        wind_direction_deg,
                        current_speed_kn,
                        current_direction_deg,
                        result_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        utc_now(),
                        selected_port,
                        v_wind,
                        dir_wind,
                        v_curr,
                        dir_curr,
                        output_df.to_json(
                            orient="records"
                        ),
                    ))

            else:

                st.error(
                    f"Calculation failed: "
                    f"{solution['reason']}"
                )


# =============================================================================
# FOOTER
# =============================================================================

st.divider()

st.caption(
    f"OpenMooring | Persistent SQLite Database | "
    f"Database: {DB_FILE}"
)
