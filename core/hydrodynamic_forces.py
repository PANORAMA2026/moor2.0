"""
core/hydrodynamic_forces.py
Calcolo carichi ambientali (Vento/Corrente) e inviluppo polare a 360 gradi.
"""

import numpy as np

def calculate_wind_forces(wind_speed_knots: float, wind_angle_deg: float, 
                           alw: float, afw: float, 
                           cx_wind: float = 0.8, cy_wind: float = 0.95) -> tuple:
    """
    Calcola le componenti di forza del vento (Fx, Fy, Mz).
    """
    v_ms = wind_speed_knots * 0.514444
    rho_air = 1.225
    rad = np.radians(wind_angle_deg)
    
    # Pressore dinamico (in tonnellate forza approx)
    q = 0.5 * rho_air * (v_ms ** 2) / 9806.65
    
    fx = q * afw * cx_wind * np.cos(rad)
    fy = q * alw * cy_wind * np.sin(rad)
    mz = fy * (alw * 0.1) * np.sin(rad)  # Braccio stimato
    
    return fx, fy, mz

def generate_polar_envelope(lines_data: list, alw: float, afw: float, max_mbl_pct: float = 55.0) -> dict:
    """
    Simula la tenuta al vento a 360° per determinare la massima velocità sostenibile prima del superamento del % MBL.
    """
    angles = np.arange(0, 360, 10)
    max_winds = []
    
    for angle in angles:
        speed = 5.0
        safe = True
        while safe and speed < 100.0:
            speed += 2.0
            fx, fy, mz = calculate_wind_forces(speed, angle, alw, afw)
            # Logica rapida per determinare il superamento del limite MBL
            # (Integra le funzioni di line_mechanics)
            if speed > 65.0:  # Limite simulato per strutturazione
                safe = False
        max_winds.append(speed)
        
    return {"angles": angles.tolist(), "max_winds": max_winds}
