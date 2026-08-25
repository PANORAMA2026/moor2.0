"""
config/constants.py
Definizione delle costanti globali dell'applicazione.
"""

# Percorso database SQLite
DB_FILE_PATH = "openmooring.db"
DB_PATH = "openmooring.db"

# Offset delle piattaforme di osservazione rispetto a prua e poppa (in metri)
OFFSET_PLATFORM_FWD_M = 25.0
OFFSET_PLATFORM_AFT_M = 14.0

# Fattori di conversione Unità di Misura (Kilonewton e Tonnellate metriche)
KN_TO_TONS = 0.1019716    # 1 kN = ~0.102 tonnellate (t o MT)
TONS_TO_KN = 9.80665      # 1 tonnellata = 9.80665 kN

# Coordinati Porti di Riferimento
PORT_COORDINATES = {
    "Long Beach Cruise Terminal": {"lat": 33.7513, "lon": -118.1888},
    "Mazatlan Pier 4/5": {"lat": 23.1994, "lon": -106.4215},
    "Mazatlan Pier 2/3": {"lat": 23.1970, "lon": -106.4200},
    "La Paz": {"lat": 24.1422, "lon": -110.3128},
    "Ensenada Pier #2": {"lat": 31.8578, "lon": -116.6258},
    "Puerto Vallarta Pier #1": {"lat": 20.6534, "lon": -105.2425},
    "Puerto Vallarta Pier #3": {"lat": 20.6550, "lon": -105.2430},
}

# Layout Bitte di Default Banchina
DEFAULT_BOLLARDS = [
    {
        "bollard_id": "B1",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 18.0,
        "Pendenza_deg": 12.0,
        "SWL_Bitta_t": 100.0,
        "Stato": "Operativa",
    },
    {
        "bollard_id": "B2",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 15.0,
        "Pendenza_deg": 8.0,
        "SWL_Bitta_t": 100.0,
        "Stato": "Operativa",
    },
    {
        "bollard_id": "B3",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 22.0,
        "Pendenza_deg": 5.0,
        "SWL_Bitta_t": 80.0,
        "Stato": "Operativa",
    },
    {
        "bollard_id": "B4",
        "Posizione": "Poppa",
        "Dist_Inclinata_m": 20.0,
        "Pendenza_deg": 6.0,
        "SWL_Bitta_t": 80.0,
        "Stato": "Operativa",
    },
    {
        "bollard_id": "B5",
        "Posizione": "Poppa",
        "Dist_Inclinata_m": 16.0,
        "Pendenza_deg": 10.0,
        "SWL_Bitta_t": 100.0,
        "Stato": "Operativa",
    },
]

# Dati di default nave
DEFAULT_SHIP = {
    "Name": "Carnival Panorama",
    "LOA": 323.44,
    "Beam": 37.20,
    "Beam_Max": 49.40,
    "Draft": 8.25,
    "Freeboard": 2.65,
    "Air_Draft_Funnel": 61.75,
    "Air_Draft_Mast": 63.25,
    "Bridge_To_Bow": 39.50,
    "Bridge_Eye_Height": 26.40,
    "AFW": 2100.0,
    "ALW": 9500.0,
    "ALC": 1800.0,
    "Wind_Load_Table": {
        10: 12.5,
        20: 50.0,
        30: 112.5,
        40: 200.0,
        50: 312.5,
    },
}
