"""
database/db_manager.py
Gestione della persistenza dati SQLite per OpenMooring MEG4 (linee, bitte, log usura e monitoraggio).
"""

import sqlite3
import pandas as pd
from config.constants import DB_FILE_PATH

def init_db():
    """
    Inizializza il database SQLite creando le tabelle necessarie se non esistono.
    """
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    
    # Tabella Registro Linee & Usura Accumulata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS line_inventory (
            line_id TEXT PRIMARY KEY,
            manufacturer TEXT,
            diameter_mm REAL,
            mbl_tons REAL,
            hours_in_service REAL DEFAULT 0,
            high_load_hours REAL DEFAULT 0,
            fatigue_cycles INTEGER DEFAULT 0,
            health_index REAL DEFAULT 100.0
        )
    ''')
    
    # Tabella Storico Monitoraggio Tensioni in Banchina
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tension_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            port_name TEXT,
            wind_speed_knots REAL,
            wind_angle_deg REAL,
            max_line_tension_tons REAL,
            max_pct_mbl REAL
        )
    ''')
    
    conn.commit()
    conn.close()

def log_mooring_session(port_name: str, wind_speed: float, wind_angle: float, max_tension: float, max_pct: float):
    """
    Registra una sessione di monitoraggio o simulazione nel database.
    """
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO tension_logs (port_name, wind_speed_knots, wind_angle_deg, max_line_tension_tons, max_pct_mbl)
        VALUES (?, ?, ?, ?, ?)
    ''', (port_name, wind_speed, wind_angle, max_tension, max_pct))
    conn.commit()
    conn.close()

def get_line_history() -> pd.DataFrame:
    """
    Recupera lo storico di usura e ore di servizio di tutte le linee registrate.
    """
    conn = sqlite3.connect(DB_FILE_PATH)
    df = pd.read_sql_query("SELECT * FROM line_inventory", conn)
    conn.close()
    return df
