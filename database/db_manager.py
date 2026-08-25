"""
database/db_manager.py

Gestione della persistenza dati SQLite per OpenMooring MEG4 
(linee, bitte, pianette mooring station, log usura e monitoraggio).
"""

from datetime import datetime
import sqlite3
import pandas as pd
from config.constants import DB_FILE_PATH


def init_db(lines_inventory_df: pd.DataFrame = None):
    """Inizializza il database SQLite ricreando le tabelle se necessario ed esegue il seeding iniziale."""
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()

    # Reset per aggiornare la struttura delle tabelle ed eliminare conflitti con vecchi schema
    cursor.execute("DROP TABLE IF EXISTS line_inventory")
    cursor.execute("DROP TABLE IF EXISTS tension_logs")
    cursor.execute("DROP TABLE IF EXISTS mooring_stations")

    # 1. Tabella Registro Linee & Usura Accumulata (con parametri materiali MEG4)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_inventory (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            manufacturer TEXT,
            material TEXT DEFAULT 'HMPE',
            diameter_mm REAL,
            mbl_tons REAL,
            tail_material TEXT DEFAULT 'NYLON',
            tail_length_m REAL DEFAULT 11.0,
            hours_in_service REAL DEFAULT 0,
            high_load_hours REAL DEFAULT 0,
            fatigue_cycles INTEGER DEFAULT 0,
            health_index REAL DEFAULT 100.0
        )
    """)

    # 2. Tabella Storico Monitoraggio Tensioni in Banchina
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tension_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            port_name TEXT,
            line_id TEXT,
            line_name TEXT,
            tension_tons REAL,
            pct_mbl REAL
        )
    """)

    # 3. Tabella Mappatura Componenti Pianetta / Stazioni d'Ormeggio
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mooring_stations (
            component_id TEXT PRIMARY KEY,
            station_name TEXT,
            component_type TEXT,
            pos_x REAL,
            pos_y REAL,
            assigned_line_id TEXT,
            FOREIGN KEY (assigned_line_id) REFERENCES line_inventory (line_id)
        )
    """)

    conn.commit()

    # Seeding iniziale del database
    if lines_inventory_df is not None and not lines_inventory_df.empty:
        cursor.execute("SELECT COUNT(*) FROM line_inventory")
        if cursor.fetchone()[0] == 0:
            for _, row in lines_inventory_df.iterrows():
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO line_inventory 
                    (line_id, line_name, manufacturer, material, diameter_mm, mbl_tons, tail_material, tail_length_m)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row.get("line_id", "")),
                        str(row.get("line_name", "")),
                        str(row.get("manufacturer", "Samson Rope")),
                        str(row.get("material", "HMPE")),
                        float(row.get("diameter_mm", 64)),
                        float(row.get("mbl_tons", 105.0)),
                        str(row.get("tail_material", "NYLON")),
                        float(row.get("tail_length_m", 11.0)),
                    ),
                )
            conn.commit()

    conn.close()


def log_mooring_session(results_df: pd.DataFrame, port_name: str):
    """Registra i risultati di tensione di una sessione di simulazione/monitoraggio."""
    if results_df is None or results_df.empty:
        return

    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for _, row in results_df.iterrows():
        line_id = str(row.get("line_id", ""))
        line_name = str(row.get("line_name", ""))
        tension = float(row.get("Tension_tons", 0.0))
        pct = float(row.get("Util_Percent", 0.0))

        # Inserimento nei log di tensione
        cursor.execute(
            """
            INSERT INTO tension_logs (timestamp, port_name, line_id, line_name, tension_tons, pct_mbl)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (now_str, port_name, line_id, line_name, tension, pct),
        )

        # Aggiornamento usura se il carico supera la soglia di guardia (> 45% MBL)
        if pct > 45.0:
            cursor.execute(
                """
                UPDATE line_inventory
                SET high_load_hours = high_load_hours + 1.0,
                    fatigue_cycles = fatigue_cycles + 1,
                    health_index = MAX(0.0, health_index - 0.5)
                WHERE line_id = ?
                """,
                (line_id,),
            )
        else:
            cursor.execute(
                """
                UPDATE line_inventory
                SET hours_in_service = hours_in_service + 1.0
                WHERE line_id = ?
                """,
                (line_id,),
            )

    conn.commit()
    conn.close()


def get_line_history() -> pd.DataFrame:
    """Recupera lo storico di usura e ore di servizio di tutte le linee registrate."""
    conn = sqlite3.connect(DB_FILE_PATH)
    df = pd.read_sql_query("SELECT * FROM line_inventory", conn)
    conn.close()
    return df


def save_mooring_station_components(components_list: list, station_name: str = "Forward Station"):
    """Salva o aggiorna i componenti mappati sulla pianetta (winches, baskets, chocks)."""
    if not components_list:
        return

    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()

    for comp in components_list:
        cursor.execute(
            """
            INSERT OR REPLACE INTO mooring_stations 
            (component_id, station_name, component_type, pos_x, pos_y, assigned_line_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(comp.get("id", "")),
                station_name,
                str(comp.get("type", "")),
                float(comp.get("x", 0.0)),
                float(comp.get("y", 0.0)),
                str(comp.get("line_id", "N/D")),
            ),
        )

    conn.commit()
    conn.close()


def get_mooring_station_components(station_name: str = "Forward Station") -> pd.DataFrame:
    """Recupera i componenti e le posizioni mappati per una determinata stazione d'ormeggio."""
    conn = sqlite3.connect(DB_FILE_PATH)
    query = "SELECT * FROM mooring_stations WHERE station_name = ?"
    df = pd.read_sql_query(query, conn, params=(station_name,))
    conn.close()
    return df
