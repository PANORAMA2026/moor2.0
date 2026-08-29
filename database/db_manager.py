"""
database/db_manager.py
Gestione della persistenza su DB SQLite per bitte, certificati, inventario,
stazioni/pianetti, setup di ormeggio per porto e storico usura cime.
"""

import os
import sqlite3
import pandas as pd
from config.constants import DB_FILE_PATH, DEFAULT_BOLLARDS

PLANS_DIR = os.path.join("assets", "planimetrie")
os.makedirs(PLANS_DIR, exist_ok=True)


def get_connection():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(default_lines_df: pd.DataFrame = None):
    """Inizializza il database SQLite creando le tabelle se non esistono e aggiorna gli schemi."""
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
            length_m REAL DEFAULT 220.0,
            station TEXT DEFAULT 'FWD',
            assigned_slot TEXT DEFAULT 'Nessuna',
            storage_type TEXT DEFAULT 'Spare Line',
            has_geolink TEXT DEFAULT 'NO',
            geolink_mbl REAL DEFAULT 0.0,
            has_tail TEXT DEFAULT 'NO',
            tail_material TEXT DEFAULT 'N/A',
            tail_diameter REAL DEFAULT 0.0,
            tail_mbl REAL DEFAULT 0.0,
            tail_length REAL DEFAULT 0.0,
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
            line_drum_a TEXT,
            line_drum_b TEXT,
            line_capstan TEXT,
            assigned_line_id TEXT,
            source_basket TEXT,
            wear_pct INTEGER,
            condition TEXT,
            last_inspection_date TEXT,
            last_inspection_note TEXT,
            PRIMARY KEY (station_name, component_id)
        )
    """)

    # MIGRAZIONE AUTOMATICA SCHEMA: station_components
    cursor.execute("PRAGMA table_info(station_components)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "last_inspection_date" not in existing_cols:
        cursor.execute("ALTER TABLE station_components ADD COLUMN last_inspection_date TEXT DEFAULT ''")
    if "last_inspection_note" not in existing_cols:
        cursor.execute("ALTER TABLE station_components ADD COLUMN last_inspection_note TEXT DEFAULT ''")

    # Tabella Metadati Stazioni
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS station_metadata (
            station_name TEXT PRIMARY KEY,
            image_path TEXT
        )
    """)

    # Tabella Storico Sessioni Generico
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

    # Tabella Setup d'Ormeggio per Porto
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS port_mooring_setups (
            port_name TEXT,
            setup_name TEXT,
            line_id TEXT,
            mbl_percentage REAL,
            is_default INTEGER DEFAULT 0,
            PRIMARY KEY (port_name, setup_name, line_id)
        )
    """)

    # Tabella Storico Accumulato Cime
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS line_life_history (
            line_id TEXT PRIMARY KEY,
            last_port TEXT,
            current_setup TEXT,
            applied_tension_mbl_pct REAL,
            total_hours REAL DEFAULT 0.0,
            accumulated_stress_index REAL DEFAULT 0.0,
            wear_percentage INTEGER DEFAULT 0,
            status TEXT DEFAULT 'BUONO',
            last_inspection TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            last_auto_sync TEXT
        )
    """)

    # MIGRAZIONE AUTOMATICA SCHEMA: line_life_history
    cursor.execute("PRAGMA table_info(line_life_history)")
    existing_life_cols = [row[1] for row in cursor.fetchall()]
    for col_name, col_type in [
        ("wear_percentage", "INTEGER DEFAULT 0"),
        ("status", "TEXT DEFAULT 'BUONO'"),
        ("last_inspection", "TEXT DEFAULT ''"),
        ("notes", "TEXT DEFAULT ''")
    ]:
        if col_name not in existing_life_cols:
            cursor.execute(f"ALTER TABLE line_life_history ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()


def assign_line_to_slot(cert_id: str, station: str, storage_type: str, assigned_slot: str):
    """Sincronizza l'assegnazione di un cavo rilasciando eventuali slot precedenti."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE certificates 
        SET assigned_slot = 'Nessuna', storage_type = 'Spare Line'
        WHERE station = ? AND assigned_slot = ? AND cert_id != ?
    """, (station, assigned_slot, cert_id))

    cursor.execute("""
        UPDATE certificates
        SET station = ?, storage_type = ?, assigned_slot = ?
        WHERE cert_id = ?
    """, (station, storage_type, assigned_slot, cert_id))

    conn.commit()
    conn.close()


def get_port_mooring_setups(port_name: str) -> dict:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM port_mooring_setups WHERE port_name = ?", 
        conn, 
        params=(port_name,)
    )
    conn.close()

    if df.empty:
        lines_df = load_lines_inventory_from_db()

        default_records = []
        if not lines_df.empty and "line_id" in lines_df.columns:
            for l_id in lines_df["line_id"].unique():
                default_records.append({"line_id": str(l_id), "mbl_percentage": 15.0})

        default_df = pd.DataFrame(default_records) if default_records else pd.DataFrame([
            {"line_id": "1", "mbl_percentage": 15.0},
            {"line_id": "2", "mbl_percentage": 15.0},
            {"line_id": "3", "mbl_percentage": 18.0},
            {"line_id": "4", "mbl_percentage": 18.0},
        ])
        return {"Default Standard": default_df}

    setups_dict = {}
    for setup_name, group in df.groupby("setup_name"):
        setups_dict[setup_name] = group[["line_id", "mbl_percentage"]].reset_index(drop=True)

    return setups_dict


def save_port_mooring_setup(port_name: str, setup_name: str, setup_df: pd.DataFrame, is_default: bool = False):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM port_mooring_setups WHERE port_name = ? AND setup_name = ?", 
        (port_name, setup_name)
    )

    for _, row in setup_df.iterrows():
        cursor.execute("""
            INSERT INTO port_mooring_setups (port_name, setup_name, line_id, mbl_percentage, is_default)
            VALUES (?, ?, ?, ?, ?)
        """, (
            port_name, 
            setup_name, 
            str(row.get("line_id")), 
            float(row.get("mbl_percentage", 15.0)), 
            1 if is_default else 0
        ))

    conn.commit()
    conn.close()


def save_line_history(history_df: pd.DataFrame):
    if history_df.empty:
        return

    conn = get_connection()
    cursor = conn.cursor()

    for _, row in history_df.iterrows():
        l_id = str(row.get("line_id", row.get("id", "")))
        last_port = str(row.get("last_port", "N/D"))
        current_setup = str(row.get("current_setup", "N/D"))
        applied_tension = float(row.get("applied_tension_mbl_pct", 0.0))
        total_hours = float(row.get("total_hours", 0.0))
        accumulated_stress = float(row.get("accumulated_stress_index", 0.0))
        wear_pct = int(row.get("wear_percentage", row.get("wear_pct", 0)))
        status = str(row.get("status", row.get("condition", "BUONO")))
        last_insp = str(row.get("last_inspection", row.get("last_inspection_date", "")))
        notes = str(row.get("notes", row.get("last_inspection_note", "")))
        last_sync = str(row.get("last_auto_sync", ""))

        cursor.execute("""
            INSERT INTO line_life_history (
                line_id, last_port, current_setup, applied_tension_mbl_pct, 
                total_hours, accumulated_stress_index, wear_percentage, status,
                last_inspection, notes, last_auto_sync
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(line_id) DO UPDATE SET
                last_port = excluded.last_port,
                current_setup = excluded.current_setup,
                applied_tension_mbl_pct = excluded.applied_tension_mbl_pct,
                total_hours = excluded.total_hours,
                accumulated_stress_index = excluded.accumulated_stress_index,
                wear_percentage = excluded.wear_percentage,
                status = excluded.status,
                last_inspection = excluded.last_inspection,
                notes = excluded.notes,
                last_auto_sync = excluded.last_auto_sync
        """, (l_id, last_port, current_setup, applied_tension, total_hours, accumulated_stress, wear_pct, status, last_insp, notes, last_sync))

    conn.commit()
    conn.close()


def get_line_history() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM line_life_history", conn)
    conn.close()

    if df.empty:
        inv_df = load_lines_inventory_from_db()
        if not inv_df.empty and "line_id" in inv_df.columns:
            df = pd.DataFrame({
                "line_id": inv_df["line_id"],
                "last_port": "N/D",
                "current_setup": "N/D",
                "applied_tension_mbl_pct": 0.0,
                "total_hours": 0.0,
                "accumulated_stress_index": 0.0,
                "wear_percentage": 0,
                "status": "BUONO",
                "last_inspection": "",
                "notes": "",
                "last_auto_sync": "Mai"
            })
    return df


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


def save_certificate_to_db(cert_dict: dict):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO certificates (
            cert_id, manufacturer, material, diameter_mm, mbl_tons, length_m,
            station, assigned_slot, storage_type, has_geolink, geolink_mbl,
            has_tail, tail_material, tail_diameter, tail_mbl, tail_length, standard, issue_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        cert_dict.get("cert_id"), cert_dict.get("manufacturer"), cert_dict.get("material"),
        cert_dict.get("diameter_mm"), cert_dict.get("mbl_tons"), cert_dict.get("length_m", 220.0),
        cert_dict.get("station", "FWD"), cert_dict.get("assigned_slot", "Nessuna"), cert_dict.get("storage_type", "Spare Line"),
        cert_dict.get("has_geolink", "NO"), cert_dict.get("geolink_mbl", 0.0),
        cert_dict.get("has_tail", "NO"), cert_dict.get("tail_material", "N/A"),
        cert_dict.get("tail_diameter", 0.0), cert_dict.get("tail_mbl", 0.0),
        cert_dict.get("tail_length", 0.0), cert_dict.get("standard", "MEG4"), cert_dict.get("issue_date", "")
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


def save_station_image_file(station_name: str, file_bytes: bytes, file_ext: str) -> str:
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
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT image_path FROM station_metadata WHERE station_name = ?", (station_name,))
    row = cursor.fetchone()
    conn.close()

    if row and row["image_path"] and os.path.exists(row["image_path"]):
        return row["image_path"]
    return None


def save_mooring_station_components(components_list: list, station_name: str):
    """Salva i componenti della stazione gestendo la mappatura flessibile dei campi del DB."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(station_components)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    if "last_inspection_date" not in existing_cols:
        cursor.execute("ALTER TABLE station_components ADD COLUMN last_inspection_date TEXT DEFAULT ''")
    if "last_inspection_note" not in existing_cols:
        cursor.execute("ALTER TABLE station_components ADD COLUMN last_inspection_note TEXT DEFAULT ''")

    cursor.execute("DELETE FROM station_components WHERE station_name = ?", (station_name,))

    for item in components_list:
        comp_id = str(item.get("comp_id", item.get("component_id", item.get("id", "ELEMENTO"))))
        comp_type = str(item.get("comp_type", item.get("component_type", item.get("type", "WINCH"))))
        
        pos_x = float(item.get("pos_x", item.get("x_pos", item.get("x", 0.0))))
        pos_y = float(item.get("pos_y", item.get("y_pos", item.get("y", 0.0))))
        
        line_id = str(item.get("line_id", "N/D"))
        line_drum_a = str(item.get("line_drum_a", "Nessuna"))
        line_drum_b = str(item.get("line_drum_b", "Nessuna"))
        line_capstan = str(item.get("line_capstan", "Nessuna"))
        assigned_line_id = str(item.get("assigned_line_id", "N/D"))
        source_basket = str(item.get("source_basket", "Nessuno"))
        
        wear_pct = int(item.get("wear_pct", 0))
        condition = str(item.get("condition", "BUONO"))
        last_insp_date = str(item.get("last_inspection_date", ""))
        last_insp_note = str(item.get("last_inspection_note", ""))

        cursor.execute("""
            INSERT INTO station_components (
                station_name, component_id, component_type, x_pos, y_pos, line_id,
                line_drum_a, line_drum_b, line_capstan, assigned_line_id, source_basket,
                wear_pct, condition, last_inspection_date, last_inspection_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            station_name, comp_id, comp_type, pos_x, pos_y, line_id,
            line_drum_a, line_drum_b, line_capstan, assigned_line_id, source_basket,
            wear_pct, condition, last_insp_date, last_insp_note
        ))

    conn.commit()
    conn.close()


def get_mooring_station_components(station_name: str) -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM station_components WHERE station_name = ?", conn, params=(station_name,))
    conn.close()
    return df


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
