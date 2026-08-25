"""
core/line_mechanics.py
Motore fisico non-lineare conforme a OCIMF MEG4 per calcoli di ormeggio e rigidezza elastica.
Predisposto per validazione Lloyd's Register.
"""

import numpy as np
import pandas as pd
from config.constants import KN_TO_TONS

# Parametri curve di allungamento MEG4 (% Elongation = A * (T / MBL)^B)
# Dati tipici di targa costruttori certificati (es. Samson, Lankhorst, Katradis)
MATERIAL_ELONGATION_PARAMS = {
    "HMPE": {"A": 0.025, "B": 0.85},       # Molto rigido
    "POLYESTER": {"A": 0.070, "B": 0.75},  # Flessibilità media
    "NYLON": {"A": 0.180, "B": 0.60},      # Molto elastico (alta assorbenza)
    "STEEL_WIRE": {"A": 0.012, "B": 1.00}  # Lineare quasi rigido
}

def get_material_stiffness(material_type: str, tension_tons: float, mbl_tons: float, length_m: float) -> float:
    """
    Calcola la rigidezza secante o tangenziale k = dT/dL (in tonnellate/metro) 
    in base alla tensione attuale e al materiale (curve non lineari MEG4).
    """
    if length_m <= 0 or mbl_tons <= 0:
        return 0.0
    
    mat_key = material_type.upper().strip()
    params = MATERIAL_ELONGATION_PARAMS.get(mat_key, MATERIAL_ELONGATION_PARAMS["HMPE"])
    
    # Rapporto di carico / pretensione minima di guardia (1% MBL)
    load_ratio = max(tension_tons / mbl_tons, 0.01)
    
    # Allungamento relativo ε = A * (T/MBL)^B
    elongation_ratio = params["A"] * (load_ratio ** params["B"])
    delta_l = length_m * elongation_ratio
    
    # Rigidezza secante kN/m convertita in tonnellate/m
    k_secant = tension_tons / max(delta_l, 0.001)
    return k_secant

def calculate_meg4_composite_stiffness(
    main_mat: str, main_mbl: float, main_len: float, main_tension: float,
    tail_mat: str, tail_mbl: float, tail_len: float
) -> float:
    """
    Calcola la rigidezza equivalente non lineare di una linea composta (Cavo + Tail).
    """
    k_main = get_material_stiffness(main_mat, main_tension, main_mbl, main_len) if main_len > 0 else 0.0
    k_tail = get_material_stiffness(tail_mat, main_tension, tail_mbl, tail_len) if tail_len > 0 else 0.0

    if k_main > 0 and k_tail > 0:
        return (k_main * k_tail) / (k_main + k_tail)
    elif k_main > 0:
        return k_main
    elif k_tail > 0:
        return k_tail
    return 0.0

def calculate_line_geometry(lines_df: pd.DataFrame, bollards_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcola vettori geometrici 3D (X, Y, Z), pendenza, azimuth e lunghezza reale delle linee.
    """
    merged = lines_df.merge(bollards_df, on="bollard_id", how="inner")
    if merged.empty:
        return pd.DataFrame()

    dx = merged["bollard_x_m"] - merged["chock_x_m"]
    dy = merged["bollard_y_m"] - merged["chock_y_m"]
    dz = merged["bollard_z_m"] - merged["chock_z_m"]

    length_3d = np.sqrt(dx**2 + dy**2 + dz**2)
    azimuth = np.degrees(np.arctan2(dy, dx))
    incline = np.degrees(np.arcsin(np.abs(dz) / np.maximum(length_3d, 0.1)))

    merged["length_m"] = np.round(length_3d, 2)
    merged["azimuth_deg"] = np.round(azimuth, 1)
    merged["incline_deg"] = np.round(incline, 1)
    merged["dx"] = dx
    merged["dy"] = dy
    merged["dz"] = dz

    return merged

def solve_line_tensions_3d(geom_df: pd.DataFrame, forces_dict: dict, max_iter: int = 15, tol: float = 1e-3) -> pd.DataFrame:
    """
    Risolutore iterativo Newton-Raphson per il bilancio di ormeggio 3D non lineare (MEG4).
    Calcola lo spostamento della nave e la distribuzione reale del carico su ogni cima.
    """
    df = geom_df.copy()
    num_lines = len(df)

    if num_lines == 0:
        df["Tension_tons"] = []
        df["Util_Percent"] = []
        return df

    # Vettore forze esterne aggregate [Fx, Fy, Mz]
    f_ext = np.array([
        forces_dict.get("Fx_total_t", 0.0),
        forces_dict.get("Fy_total_t", 0.0),
        forces_dict.get("Mz_total_tm", 0.0)
    ])

    # Inizializzazione tensioni al pretensionamento standard MEG4 (10% MBL)
    tensions = df["mbl_tons"].values * 0.10
    
    # Loop iterativo per la rigidezza tangenziale / non lineare
    for iteration in range(max_iter):
        k_global = np.zeros((3, 3))
        b_vectors = []

        for idx, row in df.iterrows():
            rad_az = np.radians(row.get("azimuth_deg", 0.0))
            rad_inc = np.radians(row.get("incline_deg", 0.0))
            x_c = row.get("chock_x_m", 0.0)
            y_c = row.get("chock_y_m", 0.0)

            # Vettore direzionale
            bx = np.cos(rad_inc) * np.cos(rad_az)
            by = np.cos(rad_inc) * np.sin(rad_az)
            bm = x_c * by - y_c * bx
            b_vec = np.array([bx, by, bm])
            b_vectors.append(b_vec)

            # Calcolo rigidezza non lineare sulla tensione dello step corrente
            mat_main = row.get("material", "HMPE")
            mat_tail = row.get("tail_material", "NYLON")
            mbl = row.get("mbl_tons", 100.0)
            l_main = row.get("length_m", 30.0)
            l_tail = row.get("tail_length_m", 11.0)

            k_eq = calculate_meg4_composite_stiffness(
                mat_main, mbl, l_main, tensions[idx],
                mat_tail, mbl, l_tail
            )

            k_global += k_eq * np.outer(b_vec, b_vec)

        # Risoluzione spostamento nave u = [dx, dy, dpsi]
        try:
            displacements = np.linalg.solve(k_global, f_ext)
        except np.linalg.LinAlgError:
            displacements = np.zeros(3)

        # Aggiornamento tensioni con limite inferiore (cime in bando non lavorano a compressione)
        new_tensions = np.zeros(num_lines)
        for i in range(num_lines):
            delta_l = np.dot(b_vectors[i], displacements)
            # Pretensione + Delta tensione elastica
            updated_t = (df.iloc[i]["mbl_tons"] * 0.10) + (k_eq * delta_l)
            new_tensions[i] = max(0.0, updated_t)

        # Controllo convergenza
        if np.max(np.abs(new_tensions - tensions)) < tol:
            tensions = new_tensions
            break
        
        tensions = new_tensions

    # Calcolo percentuali MBL finali
    utils = [(t / mbl) * 100.0 if mbl > 0 else 0.0 for t, mbl in zip(tensions, df["mbl_tons"])]

    df["Tension_tons"] = np.round(tensions, 2)
    df["Util_Percent"] = np.round(utils, 1)

    return df

def calculate_wind_operability_envelope(
    geom_df: pd.DataFrame,
    afw: float,
    alw: float,
    alc: float,
    loa: float,
    v_curr: float = 0.0,
    dir_curr: float = 0.0,
) -> tuple:
    """Calcola l'inviluppo di operabilità a 360° secondo limiti di sicurezza MEG4 (Max 55% MBL)."""
    from core.hydrodynamic_forces import calculate_environmental_forces

    angles = list(range(0, 360, 10))
    max_winds = []

    for angle in angles:
        speed = 10.0
        safe = True
        while safe and speed <= 90.0:
            forces = calculate_environmental_forces(
                speed, angle, v_curr, dir_curr, afw, alw, alc, loa
            )
            res_df = solve_line_tensions_3d(geom_df, forces)

            # Criterio di sicurezza MEG4: Nessuna cima deve superare il 55% MBL
            if (res_df["Util_Percent"] > 55.0).any():
                safe = False
            else:
                speed += 2.0

        max_winds.append(speed)

    return angles, max_winds
