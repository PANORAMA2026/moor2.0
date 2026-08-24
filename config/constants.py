"""
config/constants.py
Definizioni di costanti globali e configurazioni di default per OpenMooring MEG4.
"""

# Fattori di Conversione
KN_TO_TONS = 0.10197162129779283
TONS_TO_KN = 1.0 / KN_TO_TONS

# Coordinate di default Observation Platforms (Distanza da Prua/Poppa)
DEFAULT_BOW_PLATFORM_OFFSET = 21.0    # metri dall'estrema prua
DEFAULT_STERN_PLATFORM_OFFSET = 14.0  # metri dall'estrema poppa

# Coefficienti di Default MEG4
DEFAULT_AIR_DENSITY = 1.225   # kg/m^3
DEFAULT_WATER_DENSITY = 1025.0 # kg/m^3

# Configurazione del Database SQLite
DB_FILE_PATH = "openmooring.db"
