"""
core/line_mechanics.py
Motore fisico per il calcolo della geometria 3D, rigidezza elastica e tensionamento delle linee.
"""

import numpy as np
import pandas as pd
from config.constants import KN_TO_TONS


def calculate_composite_stiffness(
    e_main: float,
    a_main: float,
    l_main: float,
    e_tail: float,
    a_tail: float,
    l_tail: float,
) -> float:
  """Calcola la rigidezza equivalente di due molle in serie (Cavo Principale + Tail)."""
  k_main = (e_main * a_main / l_main) * KN_TO_TONS if l_main > 0 else 0.0
  k_tail = (e_tail * a_tail / l_tail) * KN_TO_TONS if l_tail > 0 else 0.0

  if k_main > 0 and k_tail > 0:
    return (k_main * k_tail) / (k_main + k_tail)
  elif k_main > 0:
    return k_main
  elif k_tail > 0:
    return k_tail
  return 0.0


def calculate_line_geometry(
    lines_df: pd.DataFrame, bollards_df: pd.DataFrame
) -> pd.DataFrame:
  """Calcola lunghezza 3D, azimuth e inclinazione di ogni cavo rispetto alla banchina."""
  merged = lines_df.merge(bollards_df, on="bollard_id", how="inner")
  if merged.empty:
    return pd.DataFrame()

  dx = merged["bollard_x_m"] - merged["chock_x_m"]
  dy = merged["bollard_y_m"] - merged["chock_y_m"]
  dz = merged["bollard_z_m"] - merged["chock_z_m"]

  length = np.sqrt(dx**2 + dy**2 + dz**2)
  azimuth = np.degrees(np.arctan2(dy, dx))
  incline = np.degrees(np.arcsin(np.abs(dz) / np.maximum(length, 0.1)))

  merged["length_m"] = np.round(length, 2)
  merged["azimuth_deg"] = np.round(azimuth, 1)
  merged["incline_deg"] = np.round(incline, 1)

  return merged


def solve_line_tensions_3d(
    geom_df: pd.DataFrame, forces_dict: dict
) -> pd.DataFrame:
  """Risolve il sistema di equazioni per distribuire le forze sui cavi d'ormeggio."""
  df = geom_df.copy()
  num_lines = len(df)

  if num_lines == 0:
    df["Tension_tons"] = []
    df["Util_Percent"] = []
    return df

  # Calcolo delle tensioni distribuite in base alla geometria
  fx = forces_dict.get("Fx_total_t", 0.0)
  fy = forces_dict.get("Fy_total_t", 0.0)

  fx_per_line = fx / num_lines
  fy_per_line = fy / num_lines

  tensions = []
  utils = []

  for idx, row in df.iterrows():
    rad_az = np.radians(row.get("azimuth_deg", 0.0))
    rad_inc = np.radians(row.get("incline_deg", 0.0))

    # Proiezione 3D
    cos_inc = np.cos(rad_inc) if np.cos(rad_inc) > 0.1 else 0.1
    t_horiz = np.sqrt(
        (fx_per_line * np.cos(rad_az)) ** 2 + (fy_per_line * np.sin(rad_az)) ** 2
    )
    t_total = t_horiz / cos_inc

    mbl = row.get("mbl_tons", 100.0)
    util = (t_total / mbl) * 100.0 if mbl > 0 else 0.0

    tensions.append(round(t_total, 2))
    utils.append(round(util, 1))

  df["Tension_tons"] = tensions
  df["Util_Percent"] = utils

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
  """Calcola l'inviluppo di operabilità a 360° per determinare la velocità limite del vento."""
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

      if (res_df["Util_Percent"] > 55.0).any():
        safe = False
      else:
        speed += 2.0

    max_winds.append(speed)

  return angles, max_winds
