"""
config/constants.py
Dati nave di default, conversioni, offset di misurazione e porti.
"""

KN_TO_TONS = 0.10197162129779

OFFSET_PLATFORM_FWD_M = 21.0  # 21 m dall'estrema prua
OFFSET_PLATFORM_AFT_M = 14.0  # 14 m dall'estrema poppa

DEFAULT_SHIP = {
    "LOA": 323.6,
    "Beam": 37.2,
    "Draft": 8.2,
    "AFW": 1250.0,
    "ALW": 6120.0,
    "ALC": 1200.0,
}

PORT_COORDINATES = {
    "Long Beach Cruise Terminal": {"lat": 33.7513, "lon": -118.1888},
    "Mazatlan Pier 4/5": {"lat": 23.1978, "lon": -106.4211},
    "Mazatlan Pier 2/3": {"lat": 23.1950, "lon": -106.4200},
    "La Paz": {"lat": 24.1422, "lon": -110.3128},
    "Ensenada Pier #2": {"lat": 31.8578, "lon": -116.6258},
    "Puerto Vallarta Pier #1": {"lat": 20.6534, "lon": -105.2403},
    "Puerto Vallarta Pier #3": {"lat": 20.6560, "lon": -105.2415},
}

DEFAULT_BOLLARDS = [
    {
        "bollard_id": "B1",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 15.0,
        "Pendenza_deg": 0.0,
        "Dist_Orizzontale_m": 15.0,
        "X_Coordinata_m": 125.8,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B2",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 25.0,
        "Pendenza_deg": 0.0,
        "Dist_Orizzontale_m": 25.0,
        "X_Coordinata_m": 115.8,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B3",
        "Posizione": "Prua",
        "Dist_Inclinata_m": 60.0,
        "Pendenza_deg": 0.0,
        "Dist_Orizzontale_m": 60.0,
        "X_Coordinata_m": 80.8,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B4",
        "Posizione": "Poppa",
        "Dist_Inclinata_m": 65.0,
        "Pendenza_deg": 0.0,
        "Dist_Orizzontale_m": 65.0,
        "X_Coordinata_m": -82.8,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 100,
        "Stato": "Attivo",
    },
    {
        "bollard_id": "B5",
        "Posizione": "Poppa",
        "Dist_Inclinata_m": 10.0,
        "Pendenza_deg": 0.0,
        "Dist_Orizzontale_m": 10.0,
        "X_Coordinata_m": -137.8,
        "Y_Coordinata_m": 25.0,
        "Z_Altezza_m": -3.0,
        "SWL_Bitta_t": 150,
        "Stato": "Attivo",
    },
]
