"""
database/db_manager.py
Gestione della persistenza su DB SQLite per bitte, certificati, inventario e storico.
"""

import sqlite3
import pandas as pd
from config.constants import DB_FILE_PATH, DEFAULT_BOLLARDS


def get_connection():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(default_lines_df: pd.DataFrame = None):
    """Inizializza il database SQLite creando le tabelle se non esistono."""
    conn = get_connection()
    cursor = conn.cursor()

    # Tabella Bitte Banchina (Persistente)
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
    """Salva o aggiorna le bitte di un determinato porto su SQLite."""
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
    """Carica le bitte di un porto dal database. Se vuoto, carica il default."""
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM port_bollards WHERE port_name = ?", conn, params=(port_name,))
    conn.close()

    if df.empty:
        df_def = pd.DataFrame(DEFAULT_BOLLARDS)
        df_def["is_frozen"] = True
        return df_def

    # Mappatura colonne per compatibilità vista
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


def log_mooring_session(results_df: pd.DataFrame, port_name: str):
    """Salva le tensioni misurate nello storico usura."""
    conn = get_connection()
    cursor = conn.cursor()
    for _, r in results_df.iterrows():
        cursor.execute("""
            INSERT INTO mooring_history (port_name, line_id, tension_tons, util_percent)
            VALUES (?, ?, ?, ?)
        """, (port_name, str(r.get("line_id")), float(r.get("Tension_tons", 0)), float(r.get("Util_Percent", 0))))
    conn.commit()
    conn.close()
