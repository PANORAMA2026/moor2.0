"""
core/line_mechanics.py
Motore fisico per il calcolo della rigidezza elastica e tensionamento delle linee.
"""

import numpy as np
from config.constants import KN_TO_TONS

def calculate_composite_stiffness(e_main: float, a_main: float, l_main: float, 
                                 e_tail: float, a_tail: float, l_tail: float) -> float:
    """
    Calcola la rigidezza equivalente di due molle in serie (Cavo Principale + Tail).
    """
    k_main = (e_main * a_main / l_main) * KN_TO_TONS if l_main > 0 else 0.0
    k_tail = (e_tail * a_tail / l_tail) * KN_TO_TONS if l_tail > 0 else 0.0
    
    if k_main > 0 and k_tail > 0:
        return (k_main * k_tail) / (k_main + k_tail)
    elif k_main > 0:
        return k_main
    elif k_tail > 0:
        return k_tail
    return 0.0

def build_global_stiffness_matrix(lines_data: list) -> np.ndarray:
    """
    Costruisce la matrice di rigidezza globale 3x3 proiettando azimuth e pendenza delle linee.
    """
    k_global = np.zeros((3, 3))
    
    for line in lines_data:
        k_eq = line.get('k_eq', 0.0)
        alpha = np.radians(line.get('azimuth', 0.0))
        phi = np.radians(line.get('elevation', 0.0))
        x_chock = line.get('x_chock', 0.0)
        y_chock = line.get('y_chock', 0.0)
        
        # Vettore direzionale e momento
        bx = np.cos(phi) * np.cos(alpha)
        by = np.cos(phi) * np.sin(alpha)
        bm = x_chock * by - y_chock * bx
        
        b_vec = np.array([bx, by, bm])
        k_global += k_eq * np.outer(b_vec, b_vec)
        
    return k_global

def solve_line_tensions(external_forces: np.ndarray, k_global: np.ndarray, lines_data: list) -> list:
    """
    Calcola il dislocamento equivalente e la tensione risultante su ciascuna linea.
    """
    try:
        displacements = np.linalg.solve(k_global, external_forces)
    except np.linalg.LinAlgError:
        displacements = np.zeros(3)

    results = []
    for line in lines_data:
        alpha = np.radians(line.get('azimuth', 0.0))
        phi = np.radians(line.get('elevation', 0.0))
        x_chock = line.get('x_chock', 0.0)
        y_chock = line.get('y_chock', 0.0)
        
        bx = np.cos(phi) * np.cos(alpha)
        by = np.cos(phi) * np.sin(alpha)
        bm = x_chock * by - y_chock * bx
        b_vec = np.array([bx, by, bm])
        
        delta_l = np.dot(b_vec, displacements)
        tension = max(0.0, line.get('k_eq', 0.0) * delta_l)
        
        mbl = line.get('mbl', 1.0)
        pct_mbl = (tension / mbl) * 100.0 if mbl > 0 else 0.0
        
        results.append({
            'line_id': line.get('id'),
            'tension_tons': tension,
            'pct_mbl': pct_mbl
        })
        
    return results
