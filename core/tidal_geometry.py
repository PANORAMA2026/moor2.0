"""Apply tidal vessel heave to mooring-line geometry.

The base mooring geometry uses fixed ship/shore coordinates. This module adds a
transparent vertical displacement of the vessel fairlead/chock coordinates so
that the line length and vertical working angle respond to the selected tidal
state. It does not alter the horizontal berth geometry.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def apply_vessel_heave_to_geometry(
    geom_df: pd.DataFrame,
    vessel_heave_m: float,
) -> pd.DataFrame:
    """Return geometry recalculated after a vertical vessel displacement.

    ``vessel_heave_m`` is positive upward. The shore bollard remains fixed,
    while the vessel chock/fairlead moves vertically with the vessel.
    """
    if geom_df is None or geom_df.empty:
        return pd.DataFrame() if geom_df is None else geom_df.copy()

    df = geom_df.copy()
    required = [
        "bollard_x_m", "bollard_y_m", "bollard_z_m",
        "chock_x_m", "chock_y_m", "chock_z_m",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing geometry fields for tidal adjustment: {', '.join(missing)}")

    effective_chock_z = pd.to_numeric(df["chock_z_m"], errors="coerce") + float(vessel_heave_m)
    dx = pd.to_numeric(df["bollard_x_m"], errors="coerce") - pd.to_numeric(df["chock_x_m"], errors="coerce")
    dy = pd.to_numeric(df["bollard_y_m"], errors="coerce") - pd.to_numeric(df["chock_y_m"], errors="coerce")
    dz = pd.to_numeric(df["bollard_z_m"], errors="coerce") - effective_chock_z

    if any(series.isna().any() for series in (dx, dy, dz)):
        raise ValueError("Invalid numeric geometry field during tidal adjustment.")

    length_3d = np.sqrt(dx**2 + dy**2 + dz**2)
    if (length_3d <= 1e-6).any():
        raise ValueError("Zero-length mooring geometry after tidal adjustment.")

    df["vessel_heave_m"] = float(vessel_heave_m)
    df["chock_z_effective_m"] = effective_chock_z
    df["length_m"] = length_3d
    df["azimuth_deg"] = np.degrees(np.arctan2(dy, dx))
    df["incline_deg"] = np.degrees(np.arcsin(np.clip(np.abs(dz) / length_3d, 0.0, 1.0)))
    df["dx"] = dx
    df["dy"] = dy
    df["dz"] = dz
    return df
