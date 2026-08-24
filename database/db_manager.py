"""database/db_manager.py

Gestione della persistenza dati SQLite per OpenMooring MEG4 (linee, bitte, log
usura e monitoraggio).
"""

from datetime import datetime
import sqlite3
from config.constants import DB_FILE_PATH
import pandas as pd


def init_db(lines_inventory_df: pd.DataFrame = None):
  """Inizializza il database SQLite creando le tabelle necessarie ed esegue il seeding iniziale."""
  conn = sqlite3.connect(DB_FILE_PATH)
  cursor = conn.cursor()

  # Tabella Registro Linee & Usura Accumulata
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_inventory (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            manufacturer TEXT,
            diameter_mm REAL,
            mbl_tons REAL,
            hours_in_service REAL DEFAULT 0,
            high_load_hours REAL DEFAULT 0,
            fatigue_cycles INTEGER DEFAULT 0,
            health_index REAL DEFAULT 100.0
        )
    """)

  # Tabella Storico Monitoraggio Tensioni in Banchina
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

  conn.commit()

  # Seeding iniziale del database se la tabella line_inventory è vuota
  if lines_inventory_df is not None and not lines_inventory_df.empty:
    cursor.execute("SELECT COUNT(*) FROM line_inventory")
    if cursor.fetchone()[0] == 0:
      for _, row in lines_inventory_df.iterrows():
        cursor.execute(
            """
                    INSERT OR IGNORE INTO line_inventory (line_id, line_name, manufacturer, diameter_mm, mbl_tons)
                    VALUES (?, ?, ?, ?, ?)
                """,
            (
                str(row.get("line_id", "")),
                str(row.get("line_name", "")),
                str(row.get("manufacturer", "Samson Rope")),
                float(row.get("diameter_mm", 64)),
                float(row.get("mbl_tons", 105.0)),
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
            INSERT INTO tension_logs (timestamp, port_name, line_id, line_name, tension_tons, max_pct_mbl)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
        (now_str, port_name, line_id, line_name, tension, pct),
    )

    # Aggiornamento usura se il carico supera la soglia di guardia (es. > 45% MBL)
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
