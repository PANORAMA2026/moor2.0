"""
database/db_manager.py
Gestione della persistenza su DB SQLite per bitte, certificati, inventario,
stazioni/pianetti (inclusi percorsi immagini) e storico.
"""

import os
import sqlite3
import pandas as pd
from config.constants import DB_FILE_PATH, DEFAULT_BOLLARDS

# Cartella per il salvataggio fisico delle immagini dei pianetti
PLANS_DIR = os.path.join("assets", "planimetrie")
os.makedirs(PLANS_DIR, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(default_lines_df: pd.DataFrame = None):
    """Inizializza il database SQLite creando le tabelle se non esistono."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabella Bitte Banchina
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS port_bollards (
            port_name TEXT,
            bollard_id TEXT,
            position_type TEXT,
            dist_inclinata_m REAL,
            pendenza_deg REAL,
            dist_orizzontale_m REAL,
            x_m REAL,
            y_m REAL,
            z_m REAL,
            swl_t REAL,
            stato TEXT,
            PRIMARY KEY (port_name, bollard_id)
        )
    """)

    # Tabella Certificati Cavi
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            cert_id TEXT PRIMARY KEY,
            manufacturer TEXT,
            material TEXT,
            diameter_mm REAL,
            mbl_tons REAL,
            standard TEXT,
            issue_date TEXT
        )
    """)

    # Tabella Inventario Linee
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lines_inventory (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            line_type TEXT,
            station_id TEXT,
            winch_id TEXT,
            cert_id TEXT,
            chock_x_m REAL,
            chock_y_m REAL,
            chock_z_m REAL,
            material TEXT,
            diameter_mm REAL,
            E_modulus_GPa REAL,
            mbl_tons REAL,
            tail_length_m REAL,
            tail_diameter_mm REAL,
            tail_E_modulus_GPa REAL,
            tail_mbl_tons REAL,
            bollard_id TEXT
        )
    """)

    # Tabella Componenti Pianetti/Stazioni
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS station_components (
            station_name TEXT,
            component_id TEXT,
            component_type TEXT,
            x_pos REAL,
            y_pos REAL,
            line_id TEXT,
            PRIMARY KEY (station_name, component_id)
        )
    """)

    # Tabella Metadati Stazioni (Immagini Pianetti Persistenti)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS station_metadata (
            station_name TEXT PRIMARY KEY,
            image_path TEXT
        )
    """)

    # Tabella Storico Sessioni
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mooring_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            port_name TEXT,
            line_id TEXT,
            tension_tons REAL,
            util_percent REAL
        )
    """)

    conn.commit()
    conn.close()


# -----------------------------------------------------------------------------
# OPERAZIONI PERSISTENTI PER LE BITTE DI BANCHINA
# -----------------------------------------------------------------------------
def save_port_bollards_to_db(port_name: str, bollards_df: pd.DataFrame):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM port_bollards WHERE port_name = ?", (port_name,))

    for _, r in bollards_df.iterrows():
        cursor.execute("""
            INSERT INTO port_bollards (
                port_name, bollard_id, position_type, dist_inclinata_m, pendenza_deg,
                dist_orizzontale_m, x_m, y_m, z_m, swl_t, stato
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            port_name, str(r.get("bollard_id")), str(r.get("Posizione", "Prua")),
            float(r.get("Dist_Inclinata_m", 0.0)), float(r.get("Pendenza_deg", 0.0)),
            float(r.get("Dist_Orizzontale_m", 0.0)), float(r.get("X_Coordinata_m", 0.0)),
            float(r.get("Y_Coordinata_m", 0.0)), float(r.get("Z_Altezza_m", 0.0)),
            float(r.get("SWL_Bitta_t", 100.0)), str(r.get("Stato", "Disponibile"))
        ))

    conn.commit()
    conn.close()


def load_port_bollards_from_db(port_name: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM port_bollards WHERE port_name = ?", conn, params=(port_name,))
    conn.close()

    if df.empty:
        df_def = pd.DataFrame(DEFAULT_BOLLARDS)
        df_def["is_frozen"] = True
        return df_def

    df = df.rename(columns={
        "position_type": "Posizione",
        "dist_inclinata_m": "Dist_Inclinata_m",
        "pendenza_deg": "Pendenza_deg",
        "dist_orizzontale_m": "Dist_Orizzontale_m",
        "x_m": "X_Coordinata_m",
        "y_m": "Y_Coordinata_m",
        "z_m": "Z_Altezza_m",
        "swl_t": "SWL_Bitta_t",
        "stato": "Stato"
    })
    df["bollard_x_m"] = df["X_Coordinata_m"]
    df["bollard_y_m"] = df["Y_Coordinata_m"]
    df["bollard_z_m"] = df["Z_Altezza_m"]
    df["is_frozen"] = True
    return df


# -----------------------------------------------------------------------------
# OPERAZIONI PERSISTENTI PER CERTIFICATI E INVENTARIO
# -----------------------------------------------------------------------------
def save_certificate_to_db(cert_dict: dict):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO certificates (cert_id, manufacturer, material, diameter_mm, mbl_tons, standard, issue_date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        cert_dict["cert_id"], cert_dict["manufacturer"], cert_dict["material"],
        cert_dict["diameter_mm"], cert_dict["mbl_tons"], cert_dict["standard"], cert_dict["issue_date"]
    ))
    conn.commit()
    conn.close()


def load_certificates_from_db() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM certificates", conn)
    conn.close()
    return df


def save_lines_inventory_to_db(lines_df: pd.DataFrame):
    conn = get_connection()
    lines_df.to_sql("lines_inventory", conn, if_exists="replace", index=False)
    conn.close()


def load_lines_inventory_from_db() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM lines_inventory", conn)
    conn.close()
    return df


# -----------------------------------------------------------------------------
# OPERAZIONI PERSISTENTI PER PIANETTI / STAZIONI & IMMAGINI
# -----------------------------------------------------------------------------
def save_station_image_file(station_name: str, file_bytes: bytes, file_ext: str) -> str:
    """Salva il file immagine su disco fisso e memorizza il path nel DB."""
    safe_name = station_name.replace(" ", "_").replace("(", "").replace(")", "").lower()
    filename = f"plan_{safe_name}{file_ext}"
    filepath = os.path.join(PLANS_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO station_metadata (station_name, image_path)
        VALUES (?, ?)
    """, (station_name, filepath))
    conn.commit()
    conn.close()

    return filepath


def get_station_image_path(station_name: str) -> str:
    """Recupera il percorso del file immagine salvato su disco per la stazione."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM station_metadata WHERE station_name = ?", (station_name,))
    row = cursor.fetchone()
    conn.close()

    if row and row["image_path"] and os.path.exists(row["image_path"]):
        return row["image_path"]
    return None


def save_mooring_station_components(components_list: list, station_name: str):
    """Salva la lista dei componenti di una stazione nel database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM station_components WHERE station_name = ?", (station_name,))

    for item in components_list:
        cursor.execute("""
            INSERT INTO station_components (station_name, component_id, component_type, x_pos, y_pos, line_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            station_name, str(item.get("id")), str(item.get("type")),
            float(item.get("x", 0.0)), float(item.get("y", 0.0)), str(item.get("line_id", "N/D"))
        ))

    conn.commit()
    conn.close()


def get_mooring_station_components(station_name: str) -> pd.DataFrame:
    """Recupera i componenti d'ormeggio salvati per una determinata stazione."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM station_components WHERE station_name = ?", conn, params=(station_name,))
    conn.close()
    return df


def get_line_history() -> pd.DataFrame:
    return load_lines_inventory_from_db()


def log_mooring_session(results_df: pd.DataFrame, port_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    for _, r in results_df.iterrows():
        cursor.execute("""
            INSERT INTO mooring_history (port_name, line_id, tension_tons, util_percent)
            VALUES (?, ?, ?, ?)
        """, (port_name, str(r.get("line_id")), float(r.get("Tension_tons", 0)), float(r.get("Util_Percent", 0))))
    conn.commit()
    conn.close()
