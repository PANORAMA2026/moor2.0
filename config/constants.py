"""
config/constants.py
Definizione delle costanti globali dell'applicazione.
"""

# Offset delle piattaforme di osservazione rispetto a prua e poppa (in metri)
OFFSET_PLATFORM_FWD_M = 25.0
OFFSET_PLATFORM_AFT_M = 14.0

# Dati di default nave
DEFAULT_SHIP = {
    "Name": "Nave Passeggeri",
    "LOA": 323.44,
    "Beam": 37.20,
    "Beam_Max": 49.40,
    "Draft": 8.25,
    "Freeboard": 2.65,
    "Air_Draft_Funnel": 61.75,
    "Air_Draft_Mast": 63.25,
    "Bridge_To_Bow": 39.50,
    "Bridge_Eye_Height": 26.40,
    "Wind_Load_Table": {
        10: 12.5,
        20: 50.0,
        30: 112.5,
        40: 200.0,
        50: 312.5,
    },
}
