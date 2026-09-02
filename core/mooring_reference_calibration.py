"""Calibration helpers for 2D mooring-station drawings over the 3D ship.

The calibration is a visual/reference layer only. It does not create solver
coordinates automatically and must be validated before engineering use.
Coordinate convention: +X bow, +Y PORT, +Z upward.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import cos, radians, sin

@dataclass(frozen=True)
class PlanCalibration:
    station: str
    anchor_u_px: float
    anchor_v_px: float
    anchor_x_m: float
    anchor_y_m: float
    anchor_z_m: float
    scale_x_m_per_px: float
    scale_y_m_per_px: float
    rotation_deg: float = 0.0

    def pixel_to_ship_xy(self, u_px: float, v_px: float) -> tuple[float, float]:
        """Map drawing pixels to ship X/Y using the calibrated anchor."""
        du = float(u_px) - self.anchor_u_px
        dv = self.anchor_v_px - float(v_px)  # image up = ship +X
        x_local = dv * self.scale_x_m_per_px
        y_local = -du * self.scale_y_m_per_px  # image left = PORT (+Y)
        a = radians(self.rotation_deg)
        x_rot = x_local * cos(a) - y_local * sin(a)
        y_rot = x_local * sin(a) + y_local * cos(a)
        return self.anchor_x_m + x_rot, self.anchor_y_m + y_rot

# Defaults are intentionally marked VISUAL-PRELIMINARY. FWD uses the PORT
# mooring-platform rectangle identified in the supplied drawing. AFT uses the
# corresponding PORT-side platform area visible in the supplied AFT drawing.
# The scales use the known 27 m / 14 m platform-to-extreme distances and the
# configured 37.20 m beam as visual calibration references. Operators can edit
# these values in the UI; they are never silently promoted to solver geometry.
DEFAULT_PLAN_CALIBRATION = {
    "FWD": PlanCalibration(
        station="FWD", anchor_u_px=75.2, anchor_v_px=187.3,
        anchor_x_m=134.72, anchor_y_m=18.60, anchor_z_m=12.15,
        scale_x_m_per_px=0.1442, scale_y_m_per_px=0.1044,
    ),
    "AFT": PlanCalibration(
        station="AFT", anchor_u_px=61.2, anchor_v_px=54.2,
        anchor_x_m=-147.72, anchor_y_m=18.60, anchor_z_m=7.65,
        scale_x_m_per_px=0.04595, scale_y_m_per_px=0.08683,
    ),
}

def get_default_calibration(station: str) -> PlanCalibration:
    key = str(station).strip().upper()
    if key not in DEFAULT_PLAN_CALIBRATION:
        raise KeyError(f"Unsupported mooring station: {station}")
    return DEFAULT_PLAN_CALIBRATION[key]
