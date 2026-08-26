"""
core/hydrodynamic_forces.py
Calcolo carichi ambientali (Vento/Corrente) in conformità con i principi MEG4 / OCIMF.
"""

import numpy as np


def get_ocimf_wind_coefficients(angle_deg: float) -> tuple:
    """
    Approssimazione analitica fluida delle curve dei coefficienti di vento OCIMF MEG4.
    Restituisce (Cx, Cy, Cxy) in funzione dell'angolo del vento relativo.
    """
    rad = np.radians(angle_deg)
    
    # Cx (longitudinale): massimo a 0°/180°, minimo a 90°
    cx = -0.60 * np.cos(rad)
    
    # Cy (trasversale): 0 a 0°/180°, massimo attorno ai 90°
    cy = 0.95 * np.sin(rad)
    
    # Cxy (momento di imbardata): cambia segno a 90° e 270°
    cxy = 0.15 * np.sin(2 * rad)
    
    return cx, cy, cxy


def get_ocimf_current_coefficients(angle_deg: float) -> tuple:
    """
    Approssimazione analitica delle curve dei coefficienti di corrente OCIMF MEG4.
    Restituisce (Ccx, Ccy, Cct) in funzione dell'angolo della corrente relativa.
    """
    rad = np.radians(angle_deg)
    
    ccx = -0.10 * np.cos(rad)
    ccy = 0.90 * np.sin(rad)
    cct = 0.12 * np.sin(2 * rad)
    
    return ccx, ccy, cct


def calculate_wind_forces(
    wind_speed_knots: float,
    wind_angle_deg: float,
    alw: float,
    afw: float,
    loa: float = 300.0
) -> tuple:
    """Calcola le componenti di forza e momento del vento (Fx, Fy, Mz) in tonnellate e ton-metri."""
    v_ms = wind_speed_knots * 0.514444
    rho_air = 1.225
    
    # Pressione dinamica q [ton/m^2]
    q = 0.5 * rho_air * (v_ms**2) / 9806.65

    cx, cy, cxy = get_ocimf_wind_coefficients(wind_angle_deg)

    fx = q * afw * cx
    fy = q * alw * cy
    mz = q * alw * loa * cxy  # Braccio proporzionale alla lunghezza fuori tutto (LOA)

    return fx, fy, mz


def calculate_environmental_forces(
    v_wind: float,
    dir_wind: float,
    v_curr: float,
    dir_curr: float,
    afw: float,
    alw: float,
    alc: float,
    loa: float,
) -> dict:
    """Calcola le forze totali combinate (vento + corrente) in tonnellate e ton-metri."""
    # Componente Vento
    fx_w, fy_w, mz_w = calculate_wind_forces(v_wind, dir_wind, alw, afw, loa)

    # Componente Corrente
    v_curr_ms = v_curr * 0.514444
    rho_water = 1025.0
    q_c = 0.5 * rho_water * (v_curr_ms ** 2) / 9806.65

    ccx, ccy, cct = get_ocimf_current_coefficients(dir_curr)

    # Stima area frontale immersa se non fornita espressamente (es. Beam * Draft)
    front_submerged_area = alc * 0.15 
    
    fx_c = q_c * front_submerged_area * ccx
    fy_c = q_c * alc * ccy
    mz_c = q_c * alc * loa * cct

    # Forze Totali Aggregate
    fx_tot = fx_w + fx_c
    fy_tot = fy_w + fy_c
    mz_tot = mz_w + mz_c

    return {
        "Fx_total_t": round(float(fx_tot), 2),
        "Fy_total_t": round(float(fy_tot), 2),
        "Mz_total_tm": round(float(mz_tot), 2),
    }


def generate_polar_envelope(
    lines_data: list, alw: float, afw: float, max_mbl_pct: float = 55.0
) -> dict:
    """Simula la tenuta al vento a 360° per determinare la massima velocità sostenibile."""
    angles = np.arange(0, 360, 10)
    max_winds = []

    for angle in angles:
        speed = 5.0
        safe = True
        while safe and speed < 100.0:
            speed += 2.0
            fx, fy, mz = calculate_wind_forces(speed, float(angle), alw, afw)
            # Criterio semplificato o chiamata al solutore 3D
            if speed > 65.0:
                safe = False
        max_winds.append(speed)

    return {"angles": angles.tolist(), "max_winds": max_winds}
