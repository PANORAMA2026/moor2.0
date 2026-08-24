"""
utils/telemetry.py
Conversione geometrica dai rilevamenti telemetrici (prua/poppa) alle coordinate 3D della banchina.
"""

import numpy as np

def calculate_bollard_coords(distance_inc: float, pitch_angle_deg: float, 
                             azimuth_deg: float, platform_type: str, 
                             loa: float, platform_offset: float = 0.0) -> tuple:
    """
    Calcola le coordinate X, Y, Z di una bitta rispetto al centro nave (0,0,0).
    
    :param distance_inc: Distanza inclinata letta dal telemetro (m)
    :param pitch_angle_deg: Angolo di pendenza/inclinazione (gradi)
    :param azimuth_deg: Rilevamento azimutale rispetto all'asse nave (gradi)
    :param platform_type: 'bow' (prua) o 'stern' (poppa)
    :param loa: Lunghezza fuori tutto della nave (m)
    :param platform_offset: Offset della piattaforma rispetto all'estremità (m)
    :return: Tuple (x_bollard, y_bollard, z_bollard)
    """
    rad_pitch = np.radians(pitch_angle_deg)
    rad_azimuth = np.radians(azimuth_deg)
    
    # Distanza orizzontale sul piano
    d_horiz = distance_inc * np.cos(rad_pitch)
    z_bollard = -distance_inc * np.sin(rad_pitch)  # Quota rispetto al ponte
    
    # Calcolo posizione X della piattaforma dal centro nave
    if platform_type.lower() == 'bow':
        x_platform = (loa / 2.0) - platform_offset
        x_bollard = x_platform + (d_horiz * np.cos(rad_azimuth))
    else:  # 'stern'
        x_platform = -(loa / 2.0) + platform_offset
        x_bollard = x_platform - (d_horiz * np.cos(rad_azimuth))
        
    y_bollard = d_horiz * np.sin(rad_azimuth)
    
    return round(x_bollard, 2), round(y_bollard, 2), round(z_bollard, 2)
