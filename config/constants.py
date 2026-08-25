"""
config/constants.py
Costanti globali, parametri predefiniti di bordo e dati tecnici delle navi.
"""

# Offsets ufficiali delle Observation Platforms dalle estremità della nave (m)
OFFSET_PLATFORM_FWD_M = 25.0  # Observation Platform Prua (25m dall'estrema prua)
OFFSET_PLATFORM_AFT_M = 14.0  # Observation Platform Poppa (14m dall'estrema poppa)

# Dati predefiniti della nave (Piattaforma Carnival Vista/Horizon/Panorama Class)
DEFAULT_SHIP = {
    # Dati identificativi e generali
    "Name": "Carnival Panorama / Horizon Class",
    "IMO": "IMO 9767091",
    "Call_Sign": "H3WI",
    # Dimensioni principali (Pilot Card)
    "LOA": 323.44,  # Length Overall (m)
    "LBP": 286.90,  # Length Between Perpendiculars (m)
    "Beam": 37.20,  # Beam / Breadth Hull (m)
    "Beam_Max": 49.40,  # Max Breadth inclusa estensione Alette di Plancia (m)
    # Pescaggi e Altezze (Pilot Card)
    "Draft_Max": 8.55,  # Pescaggio Massimo (m)
    "Draft": 8.25,  # Pescaggio Operativo Standard (m)
    "Air_Draft_Mast": 63.25,  # Air Draft fino all'albero (m)
    "Air_Draft_Funnel": 61.75,  # Air Draft fino al fumaiolo (m)
    "Freeboard": 2.65,  # Bordo Libero (m)
    # Geometria Plancia e Riferimenti
    "Bridge_To_Bow": 39.50,  # Distanza Plancia -> Prua (m)
    "Bridge_To_Stern": 283.90,  # Distanza Plancia -> Poppa (m)
    "Bridge_Eye_Height": 26.40,  # Altezza occhi in plancia da linea di galleggiamento (m)
    # Superfici ed Esposizione
    "Wind_Sail_Area": 12022.50,  # Superficie velica totale esposta al vento (m²)
    # Carico del Vento (Wind Load Data da Grafico in Tonnellate per Nodi)
    "Wind_Load_Table": {
        15: 42.0,  # 15 Nodi -> 42 T
        20: 69.0,  # 20 Nodi -> 69 T
        25: 112.0,  # 25 Nodi -> 112 T
        30: 155.0,  # 30 Nodi -> 155 T
    },
    # Propulsione e Manovra
    "Thrusters_Bow_Power_kW": 7500.0,  # 3 x 2500 kW
    "Azipods_Power_kW": 33000.0,  # 2 x 16500 kW
}
