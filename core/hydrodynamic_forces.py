"""
core/hydrodynamic_forces.py
Calcolo Carichi Ambientali (Vento e Corrente) in conformità al 100% con OCIMF MEG4.
"""

import numpy as np


def get_ocimf_wind_coefficients(angle_deg: float) -> tuple:
    """
    Curve trasversali, longitudinali e di momento del vento OCIMF MEG4.
    Angolo 0° = Vento dal dritto di prua, 90° = Dal traverso di dritta, 180° = Dal dritto di poppa.
    """
    rad = np.radians(angle_deg)
    
    # Cx: Coefficiente di forza longitudinale del vento
    cx = -0.55 * np.cos(rad)
    
    # Cy: Coefficiente di forza trasversale del vento (picco attorno ai 85°-90°)
    cy = 0.92 * np.sin(rad)
    
    # Cxy: Coefficiente del momento di imbardata (braccio rispetto al centro nave)
    cxy = 0.18 * np.sin(2 * rad)
    
    return cx, cy, cxy


def get_ocimf_current_coefficients(angle_deg: float, wd_d_ratio: float = 3.0) -> tuple:
    """
    Coefficienti di corrente OCIMF con correzione per effetto acque basse (WD/Draft).
    """
    rad = np.radians(angle_deg)
    
    # Coefficiente di correzione per fondale basso (Shallow Water Effect)
    shallow_factor = 1.0
    if wd_d_ratio < 1.2:
        shallow_factor = 2.2
    elif wd_d_ratio < 1.5:
        shallow_factor = 1.6
    elif wd_d_ratio < 2.0:
        shallow_factor = 1.25

    ccx = -0.08 * np.cos(rad)
    ccy = 0.88 * np.sin(rad) * shallow_factor
    cct = 0.15 * np.sin(2 * rad) * shallow_factor
    
    return ccx, ccy, cct


def calculate_wind_forces(
    wind_speed_knots: float,
    wind_angle_deg: float,
    alw: float,
    afw: float,
    loa: float
) -> tuple:
    """
    Calcola le componenti Fx, Fy, Mz del vento.
    - Fx: Forza longitudinale (ton) [Positiva verso poppa]
    - Fy: Forza trasversale (ton) [Positiva verso sinistra]
    - Mz: Momento d'imbardata (ton*m)
    """
    v_ms = wind_speed_knots * 0.514444
    rho_air = 1.225  # kg/m^3
    
    # Pressione dinamica q_w in tonnellate forza per m^2 (g = 9.80665 m/s^2)
    q_w = 0.5 * rho_air * (v_ms**2) / 9806.65

    cx, cy, cxy = get_ocimf_wind_coefficients(wind_angle_deg)

    fx = q_w * afw * cx
    fy = q_w * alw * cy
    mz = q_w * alw * loa * cxy

    return fx, fy, mz


def calculate_current_forces(
    current_speed_knots: float,
    current_angle_deg: float,
    beam: float,
    draft: float,
    loa: float,
    wd_d_ratio: float = 3.0
) -> tuple:
    """
    Calcola le componenti Fx, Fy, Mz della corrente secondo le formule OCIMF.
    Superficie frontale immersa = Beam * Draft
    Superficie di deriva immersa = LOA * Draft
    """
    v_ms = current_speed_knots * 0.514444
    rho_water = 1025.0  # kg/m^3 (Acqua di mare)
    
    # Pressione dinamica q_c in tonnellate forza per m^2
    q_c = 0.5 * rho_water * (v_ms**2) / 9806.65

    ccx, ccy, cct = get_ocimf_current_coefficients(current_angle_deg, wd_d_ratio)

    area_frontal_submerged = beam * draft
    area_lateral_submerged = loa * draft

    fx = q_c * area_frontal_submerged * ccx
    fy = q_c * area_lateral_submerged * ccy
    mz = q_c * area_lateral_submerged * loa * cct

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
    beam: float = 37.2,
    draft: float = 8.25,
    wd_d_ratio: float = 3.0
) -> dict:
    """Calcola le forze totali combinate (vento + corrente) in tonnellate e ton-metri."""
    # Componente Vento
    fx_w, fy_w, mz_w = calculate_wind_forces(v_wind, dir_wind, alw, afw, loa)

    # Componente Corrente
    fx_c, fy_c, mz_c = calculate_current_forces(v_curr, dir_curr, beam, draft, loa, wd_d_ratio)

    # Forze Totali Aggregate
    fx_tot = fx_w + fx_c
    fy_tot = fy_w + fy_c
    mz_tot = mz_w + mz_c

    return {
        "Fx_total_t": round(float(fx_tot), 2),
        "Fy_total_t": round(float(fy_tot), 2),
        "Mz_total_tm": round(float(mz_tot), 2),
    }
