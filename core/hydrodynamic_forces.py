"""
core/hydrodynamic_forces.py
Calcolo carichi ambientali (Vento/Corrente) in conformità con gli standard MEG4.
"""

import numpy as np


def calculate_wind_forces(
    wind_speed_knots: float,
    wind_angle_deg: float,
    alw: float,
    afw: float,
    cx_wind: float = 0.8,
    cy_wind: float = 0.95,
) -> tuple:
  """Calcola le componenti di forza del vento (Fx, Fy, Mz)."""
  v_ms = wind_speed_knots * 0.514444
  rho_air = 1.225
  rad = np.radians(wind_angle_deg)

  # Pressione dinamica in tonnellate forza
  q = 0.5 * rho_air * (v_ms**2) / 9806.65

  fx = q * afw * cx_wind * np.cos(rad)
  fy = q * alw * cy_wind * np.sin(rad)
  mz = fy * (alw * 0.05) * np.sin(rad)

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
  fx_w, fy_w, mz_w = calculate_wind_forces(v_wind, dir_wind, alw, afw)

  # Componente Corrente (Stima semplificata MEG4)
  rad_c = np.radians(dir_curr)
  q_c = 0.5 * 1025 * ((v_curr * 0.514444) ** 2) / 9806.65
  fx_c = q_c * (alc * 0.1) * np.cos(rad_c)
  fy_c = q_c * alc * np.sin(rad_c)
  mz_c = fy_c * (loa * 0.1) * np.sin(rad_c)

  # Forze Totali
  fx_tot = fx_w + fx_c
  fy_tot = fy_w + fy_c
  mz_tot = mz_w + mz_c

  return {
      "Fx_total_t": round(fx_tot, 2),
      "Fy_total_t": round(fy_tot, 2),
      "Mz_total_tm": round(mz_tot, 2),
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
      fx, fy, mz = calculate_wind_forces(speed, angle, alw, afw)
      if speed > 65.0:
        safe = False
    max_winds.append(speed)

  return {"angles": angles.tolist(), "max_winds": max_winds}
