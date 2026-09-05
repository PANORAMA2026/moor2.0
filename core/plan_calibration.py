"""2D drawing -> ship coordinate calibration.

The transform is intentionally explicit: the operator supplies three or more
corresponding drawing points and known ship X/Y coordinates. No scale or offset
is guessed from pixels.
"""
from __future__ import annotations

import math
import sqlite3
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from config.constants import DB_FILE_PATH


def fit_affine(points_px: Sequence[Sequence[float]], points_xy_m: Sequence[Sequence[float]]):
    """Fit x=a11*px+a12*py+a13, y=a21*px+a22*py+a23.

    Requires >=3 non-collinear control points. Returns coefficients and RMS error.
    """
    if len(points_px) != len(points_xy_m) or len(points_px) < 3:
        raise ValueError("At least 3 corresponding control points are required")
    A = np.array([[float(p[0]), float(p[1]), 1.0] for p in points_px], dtype=float)
    if np.linalg.matrix_rank(A) < 3:
        raise ValueError("Control points are collinear; affine calibration is undefined")
    target = np.array([[float(p[0]), float(p[1])] for p in points_xy_m], dtype=float)
    coef, *_ = np.linalg.lstsq(A, target, rcond=None)
    pred = A @ coef
    err = np.sqrt(np.mean(np.sum((pred - target) ** 2, axis=1)))
    return coef, float(err)


def apply_affine(px: float, py: float, coef) -> tuple[float, float]:
    p = np.array([float(px), float(py), 1.0])
    out = p @ np.asarray(coef)
    return float(out[0]), float(out[1])


def save_calibration(station_name: str, drawing_width_px: float, drawing_height_px: float,
                     coef, rms_error_m: float):
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS mooring_plan_calibration(
        station_name TEXT PRIMARY KEY, drawing_width_px REAL, drawing_height_px REAL,
        rms_error_m REAL, method TEXT DEFAULT 'AFFINE_3_POINT',
        a11 REAL,a12 REAL,a13 REAL,a21 REAL,a22 REAL,a23 REAL)""")
    c = np.asarray(coef)
    conn.execute("""INSERT INTO mooring_plan_calibration
        (station_name,drawing_width_px,drawing_height_px,rms_error_m,method,a11,a12,a13,a21,a22,a23)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(station_name) DO UPDATE SET
        drawing_width_px=excluded.drawing_width_px,drawing_height_px=excluded.drawing_height_px,
        rms_error_m=excluded.rms_error_m,method=excluded.method,a11=excluded.a11,a12=excluded.a12,
        a13=excluded.a13,a21=excluded.a21,a22=excluded.a22,a23=excluded.a23""",
        (station_name,drawing_width_px,drawing_height_px,rms_error_m,"AFFINE_3_POINT",
         float(c[0,0]),float(c[1,0]),float(c[2,0]),float(c[0,1]),float(c[1,1]),float(c[2,1])))
    conn.commit(); conn.close()


def load_calibration(station_name: str):
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    try:
        row = conn.execute("SELECT * FROM mooring_plan_calibration WHERE station_name=?", (station_name,)).fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    if row is None:
        return None
    return np.array([[row[5], row[6]], [row[7], row[8]], [row[9], row[10]]], dtype=float), float(row[3])
