"""
utils/telemetry.py
Conversione geometrica dai rilevamenti telemetrici (prua/poppa) alle coordinate 3D della banchina.
"""

import numpy as np


def calculate_bollard_coords(
    distance_inc: float,
    pitch_angle_deg: float,
    azimuth_deg: float,
    platform_type: str,
    loa: float,
    platform_offset: float = 0.0,
) -> tuple:
    """Calcola le coordinate X, Y, Z di una bitta rispetto al centro nave (0,0,0).

    :param distance_inc: Distanza inclinata letta dal telemetro (m)
    :param pitch_angle_deg: Angolo di pendenza/inclinazione verticale (gradi)
    :param azimuth_deg: Rilevamento azimutale o orizzontale (gradi)
    :param platform_type: 'bow' (prua) o 'stern' (poppa)
    :param loa: Lunghezza fuori tutto della nave (m)
    :param platform_offset: Offset della piattaforma rispetto all'estremità (m)
    :return: Tuple (x_bollard, y_bollard, z_bollard)
    """
    rad_pitch = np.radians(pitch_angle_deg)
    rad_azimuth = np.radians(azimuth_deg)

    # Distanza orizzontale sul piano d'acqua/banchina
    d_horiz = distance_inc * np.cos(rad_pitch)
    z_bollard = -distance_inc * np.sin(rad_pitch)  # Quota sotto il ponte

    # Componenti orizzontali basate sull'azimut
    dx = d_horiz * np.cos(rad_azimuth)
    dy = d_horiz * np.sin(rad_azimuth)

    # Posizionamento X globale rispetto al centro nave (LOA/2)
    if platform_type.lower() == "bow":
        x_platform = (loa / 2.0) - platform_offset
        x_bollard = x_platform + dx
    else:  # 'stern'
        x_platform = -(loa / 2.0) + platform_offset
        x_bollard = x_platform - dx

    y_bollard = dy

    return round(x_bollard, 2), round(y_bollard, 2), round(z_bollard, 2)
