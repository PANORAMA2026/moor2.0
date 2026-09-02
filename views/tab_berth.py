"""3D berth layout UI: fixed berth geometry + movable ship."""
from __future__ import annotations

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import DEFAULT_SHIP
from core.berth_profiles import (
    get_berth_profile,
    list_berth_profiles,
    bollard_points_as_dicts,
)
from database.db_manager import load_port_bollards_from_db


def _profile_dataframe(selected_port: str):
    """Return berth points in the common x/y/z schema used by the 3D scene."""
    if selected_port in list_berth_profiles():
        profile = get_berth_profile(selected_port)
        return (
            pd.DataFrame(bollard_points_as_dicts(selected_port)),
            float(profile["survey_water_level_m"]),
        )

    df = load_port_bollards_from_db(selected_port)
    if df.empty:
        return pd.DataFrame(), None

    return (
        df.rename(
            columns={
                "X_Coordinata_m": "x_m",
                "Y_Coordinata_m": "y_m",
                "Z_Altezza_m": "z_m",
            }
        ),
        None,
    )


def _ship_box_mesh(x0: float, y0: float, z0: float, lx: float, by: float, h: float):
    """Simple closed 3D ship hull mesh, suitable for the berth layout view."""
    x1, x2 = x0 - lx / 2.0, x0 + lx / 2.0
    y1, y2 = y0 - by / 2.0, y0 + by / 2.0
    z1, z2 = z0, z0 + h

    # Bottom and deck rectangles.  The end sections are tapered slightly to
    # give the model a recognizable ship-like appearance rather than a box.
    bow_x = x2
    stern_x = x1
    mid = [x1, x0, x2]
    half_beams = [by * 0.34, by / 2.0, by * 0.40]

    verts = []
    for xx, half_b in zip(mid, half_beams):
        verts.extend([
            (xx, y0 - half_b, z1),
            (xx, y0 + half_b, z1),
            (xx, y0 - half_b, z2),
            (xx, y0 + half_b, z2),
        ])

    # Six vertices per side are enough for a stable simplified hull surface.
    i = list(range(len(verts)))
    faces = [
        # port side
        (0, 4, 6), (0, 6, 2), (4, 8, 10), (4, 10, 6),
        # starboard side
        (1, 3, 7), (1, 7, 5), (5, 7, 11), (5, 11, 9),
        # bottom
        (0, 1, 5), (0, 5, 4), (4, 5, 9), (4, 9, 8),
        # deck
        (2, 6, 7), (2, 7, 3), (6, 10, 11), (6, 11, 7),
        # stern / bow closure
        (0, 2, 3), (0, 3, 1), (8, 9, 11), (8, 11, 10),
    ]
    ii, jj, kk = zip(*faces)
    return verts, list(ii), list(jj), list(kk)


def _add_ship_model(fig: go.Figure, ship: dict, offset: float):
    """Restore the interactive 3D ship model and basic superstructure."""
    loa = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    beam = float(ship.get("Beam", DEFAULT_SHIP["Beam"]))
    freeboard = float(ship.get("Freeboard", DEFAULT_SHIP.get("Freeboard", 2.65)))
    bridge_h = float(ship.get("Bridge_Eye_Height", 26.4))
    mast_h = float(ship.get("Air_Draft_Mast", 63.25))

    # Main hull: z=0 is the berth/survey reference plane used by the layout.
    verts, ii, jj, kk = _ship_box_mesh(offset, 0.0, 0.0, loa, beam, max(3.0, freeboard))
    vx, vy, vz = zip(*verts)
    fig.add_trace(
        go.Mesh3d(
            x=vx, y=vy, z=vz, i=ii, j=jj, k=kk,
            opacity=0.78,
            name="Carnival Panorama — Hull",
            hovertemplate="Nave<extra></extra>",
            showscale=False,
        )
    )

    # Main deck line.
    fig.add_trace(
        go.Scatter3d(
            x=[offset - loa / 2, offset + loa / 2],
            y=[0, 0],
            z=[freeboard, freeboard],
            mode="lines",
            line=dict(width=4),
            name="Main Deck",
            showlegend=False,
        )
    )

    # Simplified superstructure, kept proportional to the vessel profile.
    super_x1 = offset - loa * 0.18
    super_x2 = offset + loa * 0.25
    super_y = beam * 0.34
    super_z1 = freeboard
    super_z2 = max(bridge_h, freeboard + 10.0)
    sx = [super_x1, super_x2, super_x2, super_x1, super_x1, super_x2, super_x2, super_x1]
    sy = [-super_y, -super_y, super_y, super_y, -super_y, -super_y, super_y, super_y]
    sz = [super_z1, super_z1, super_z1, super_z1, super_z2, super_z2, super_z2, super_z2]
    faces = [
        (0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6),
        (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2),
        (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0),
    ]
    fi, fj, fk = zip(*faces)
    fig.add_trace(
        go.Mesh3d(
            x=sx, y=sy, z=sz, i=fi, j=fj, k=fk,
            opacity=0.60,
            name="Superstructure",
            hovertemplate="Sovrastruttura<extra></extra>",
            showscale=False,
        )
    )

    # Funnel / mast marker to recover the vertical scale of the ship model.
    funnel_x = offset + loa * 0.17
    fig.add_trace(
        go.Scatter3d(
            x=[funnel_x, funnel_x], y=[0, 0], z=[super_z2, mast_h],
            mode="lines",
            line=dict(width=8),
            name="Mast / Air Draft",
            hovertemplate="Air draft %.1f m<extra></extra>" % mast_h,
        )
    )

    # Mooring deck reference points: forward and aft platform positions.
    fwd_x = offset + (loa / 2.0 - 27.0)
    aft_x = offset - (loa / 2.0 - 14.0)
    platform_z = freeboard
    fig.add_trace(
        go.Scatter3d(
            x=[fwd_x, aft_x], y=[-beam / 2.0, -beam / 2.0], z=[platform_z, platform_z],
            mode="markers+text",
            marker=dict(size=5),
            text=["FWD Mooring Station", "AFT Mooring Station"],
            textposition="middle left",
            name="Mooring Stations",
        )
    )


def _add_berth(fig: go.Figure, bollards: pd.DataFrame, ship: dict, offset: float):
    """Render the fixed berth and every surveyed bollard in the same 3D scene."""
    if bollards.empty or not {"x_m", "y_m"}.issubset(bollards.columns):
        return

    z = bollards["z_m"] if "z_m" in bollards.columns else pd.Series([0.0] * len(bollards))
    labels = []
    for _, row in bollards.iterrows():
        station = str(row.get("measurement_station", ""))
        side = str(row.get("side", ""))
        labels.append(f"{row.get('bollard_id', '')} — {station} {side}".strip())

    fig.add_trace(
        go.Scatter3d(
            x=bollards["x_m"], y=bollards["y_m"], z=z,
            mode="markers+text",
            text=bollards["bollard_id"].astype(str),
            textposition="top center",
            customdata=labels,
            marker=dict(size=7, symbol="diamond"),
            name="Bitte Banchina — FISSE",
            hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>",
        )
    )

    # Connect the surveyed points as the berth edge/reference line.
    order = bollards.sort_values("x_m")
    z_order = order["z_m"] if "z_m" in order.columns else [0.0] * len(order)
    fig.add_trace(
        go.Scatter3d(
            x=order["x_m"], y=order["y_m"], z=z_order,
            mode="lines",
            line=dict(width=3, dash="dash"),
            name="Berth Reference",
        )
    )


def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float):
    fig = go.Figure()
    _add_ship_model(fig, ship, offset)
    _add_berth(fig, bollards, ship, offset)

    # Add the water/survey reference plane only as a visual reference.
    if not bollards.empty and {"x_m", "y_m"}.issubset(bollards.columns):
        xmin = min(float(bollards["x_m"].min()), offset - float(ship.get("LOA", DEFAULT_SHIP["LOA"])) / 2) - 30
        xmax = max(float(bollards["x_m"].max()), offset + float(ship.get("LOA", DEFAULT_SHIP["LOA"])) / 2) + 30
        yvals = bollards["y_m"].astype(float)
        ymin, ymax = float(yvals.min()) - 35, max(float(yvals.max()) + 10, float(ship.get("Beam", 37.2)) / 2 + 10)
        fig.add_trace(
            go.Mesh3d(
                x=[xmin, xmax, xmax, xmin],
                y=[ymin, ymin, ymax, ymax],
                z=[0, 0, 0, 0],
                i=[0, 0], j=[1, 2], k=[2, 3],
                opacity=0.12,
                name="Survey / Berth Reference Plane",
                showlegend=False,
            )
        )

    fig.update_layout(
        height=720,
        margin=dict(l=0, r=0, t=30, b=0),
        scene=dict(
            xaxis_title="X — Longitudinale (m)",
            yaxis_title="Y — Trasversale (m)",
            zaxis_title="Z — Quota (m)",
            aspectmode="auto",
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.10)),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    return fig


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")

    for k, v in DEFAULT_SHIP.items():
        ship_dict.setdefault(k, v)

    offset = float(st.session_state.get("offset_fugro_m", 0.0))
    df, survey_level = _profile_dataframe(selected_port)
    real = selected_port in list_berth_profiles() and not df.empty

    if real:
        st.success("✅ Berth Profile reale attivo — bitte fisse sulla banchina")
        st.caption(
            f"Rilievo: livello acqua +{survey_level:.2f} m. "
            "La nave è mobile esclusivamente lungo l'asse longitudinale; le bitte restano fisse."
        )
    else:
        st.info("ℹ️ Nessun Berth Profile di rilievo disponibile per questa banchina.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Nave", ship_dict.get("Name", "N/A"))
    c2.metric("Longitudinal Offset", f"{offset:+.1f} m")
    c3.metric("Bitte", str(len(df)))

    new_offset = st.number_input(
        "Longitudinal Offset — + verso PRUA / − verso POPPA (m)",
        value=offset,
        step=0.5,
        format="%.1f",
        key="berth_longitudinal_offset",
    )
    st.session_state["offset_fugro_m"] = float(new_offset)

    if not df.empty:
        st.subheader("🧭 Modello 3D Nave + Banchina + Bitte")
        st.caption(
            "Vista interattiva: ruota con il mouse, zoom e pan. "
            "La posizione della nave cambia con il solo offset longitudinale; "
            "le coordinate delle bitte sono quelle del rilievo."
        )
        st.plotly_chart(
            _figure_3d(ship_dict, df, float(new_offset)),
            use_container_width=True,
            config={"displaylogo": False, "scrollZoom": True},
        )

        with st.expander("📐 Coordinate delle bitte", expanded=False):
            cols = [
                c for c in [
                    "bollard_id",
                    "measurement_station",
                    "side",
                    "x_m",
                    "y_m",
                    "z_m",
                    "survey_water_level_m",
                ] if c in df.columns
            ]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)

        if real:
            st.caption(
                "Le bitte sono elementi fissi della banchina. L'offset muove il modello nave, "
                "non la banchina. Il livello +0.20 m è mantenuto come riferimento del rilievo."
            )
    else:
        st.warning("Nessuna geometria di banchina disponibile per questo porto.")
