"""3D berth layout: original Carnival Panorama GLB + fixed surveyed bollards."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import trimesh

from config.constants import DEFAULT_SHIP
from core.berth_profiles import bollard_points_as_dicts, get_berth_profile, list_berth_profiles
from database.db_manager import load_port_bollards_from_db

GLB_MODEL_PATH = Path(__file__).resolve().parent.parent / "asset" / "carnivalpanorama.glb"


@st.cache_resource(show_spinner=False)
def load_ship_glb(path: str):
    """Load the original Carnival Panorama CAD model from asset/."""
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        geometries = [g.copy() for g in loaded.geometry.values()]
        if not geometries:
            raise ValueError("The GLB scene contains no geometry")
        return trimesh.util.concatenate(geometries)
    return loaded


def ship_mesh_to_plotly(mesh, ship_length_m: float, ship_beam_m: float, draft_m: float, offset_x: float = 0.0):
    """Restore the original CAD axis/scaling logic used by the application."""
    vertices = np.asarray(mesh.vertices, dtype=float).copy()
    faces = np.asarray(mesh.faces, dtype=int)
    if vertices.size == 0 or faces.size == 0:
        raise ValueError("Empty ship mesh")

    extents = np.ptp(vertices, axis=0)
    sorted_indices = np.argsort(extents)[::-1]
    idx_x = int(sorted_indices[0])
    idx_z = int(sorted_indices[1])
    idx_y = int(sorted_indices[2])

    aligned = np.zeros_like(vertices)
    # Original model convention: reverse the longest CAD axis so bow is +X.
    aligned[:, 0] = -vertices[:, idx_x]
    aligned[:, 1] = vertices[:, idx_y]
    aligned[:, 2] = vertices[:, idx_z]

    current_loa = np.ptp(aligned[:, 0])
    current_beam = np.ptp(aligned[:, 1])
    scale_x = ship_length_m / current_loa if current_loa else 1.0
    scale_y = ship_beam_m / current_beam if current_beam else 1.0
    scale_z = (scale_x + scale_y) / 2.0

    aligned[:, 0] *= scale_x
    aligned[:, 1] *= scale_y
    aligned[:, 2] *= scale_z

    min_x, max_x = aligned[:, 0].min(), aligned[:, 0].max()
    min_y, max_y = aligned[:, 1].min(), aligned[:, 1].max()
    min_z = aligned[:, 2].min()

    # Ship centre is X=0; keel is at -draft; only longitudinal offset moves it.
    aligned[:, 0] = aligned[:, 0] - (min_x + max_x) / 2.0 + offset_x
    aligned[:, 1] = aligned[:, 1] - (min_y + max_y) / 2.0
    aligned[:, 2] = aligned[:, 2] - min_z - draft_m

    return aligned, faces


def _profile_dataframe(selected_port: str) -> tuple[pd.DataFrame, float | None]:
    """Use the fixed surveyed berth profile whenever one exists."""
    if selected_port in list_berth_profiles():
        profile = get_berth_profile(selected_port)
        return pd.DataFrame(bollard_points_as_dicts(selected_port)), float(profile["survey_water_level_m"])

    df = load_port_bollards_from_db(selected_port)
    if df.empty:
        return pd.DataFrame(), None
    return df.rename(columns={
        "X_Coordinata_m": "x_m",
        "Y_Coordinata_m": "y_m",
        "Z_Altezza_m": "z_m",
    }), None


def _add_ship(fig: go.Figure, ship: dict, offset: float) -> None:
    loa = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    beam = float(ship.get("Beam", DEFAULT_SHIP["Beam"]))
    draft = float(ship.get("Draft", DEFAULT_SHIP["Draft"]))

    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")

    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, faces = ship_mesh_to_plotly(mesh, loa, beam, draft, offset)
    fig.add_trace(go.Mesh3d(
        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color="gainsboro", flatshading=True, opacity=0.96,
        name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip",
    ))

    # Bridge wings/reference line, as in the original tab.
    bridge_bow = float(ship.get("Bridge_To_Bow", DEFAULT_SHIP.get("Bridge_To_Bow", 39.5)))
    bridge_eye = float(ship.get("Bridge_Eye_Height", DEFAULT_SHIP.get("Bridge_Eye_Height", 26.4)))
    beam_max = float(ship.get("Beam_Max", DEFAULT_SHIP.get("Beam_Max", beam)))
    bridge_x = loa / 2.0 - bridge_bow + offset
    wing_y = beam_max / 2.0
    fig.add_trace(go.Scatter3d(
        x=[bridge_x, bridge_x], y=[-wing_y, wing_y], z=[bridge_eye, bridge_eye],
        mode="lines+markers", line=dict(width=7), marker=dict(size=4),
        name="Bridge Wings", hoverinfo="skip",
    ))


def _add_fixed_berth(fig: go.Figure, bollards: pd.DataFrame) -> None:
    if bollards.empty or not {"x_m", "y_m"}.issubset(bollards.columns):
        return

    z = pd.to_numeric(bollards.get("z_m", 0.0), errors="coerce").fillna(0.0)
    labels = [
        f"{r.get('measurement_station', '')} — {r.get('bollard_id', '')} — {r.get('side', '')}"
        for _, r in bollards.iterrows()
    ]

    # Every surveyed bollard is fixed to the berth. No ship offset is applied here.
    fig.add_trace(go.Scatter3d(
        x=pd.to_numeric(bollards["x_m"]),
        y=pd.to_numeric(bollards["y_m"]),
        z=z,
        mode="markers+text",
        text=[str(v) for v in bollards["bollard_id"]],
        textposition="top center",
        customdata=labels,
        marker=dict(size=8, symbol="diamond"),
        name="Ensenada Pier #2 — PORT Bollards",
        hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>",
    ))

    # Berth reference lines are drawn separately FWD/AFT to avoid artificial
    # connections between the two measurement stations.
    for station in ("FWD", "AFT"):
        part = bollards[bollards.get("measurement_station", "") == station].sort_values("x_m")
        if len(part) >= 2:
            pz = pd.to_numeric(part.get("z_m", 0.0), errors="coerce").fillna(0.0)
            fig.add_trace(go.Scatter3d(
                x=part["x_m"], y=part["y_m"], z=pz,
                mode="lines", line=dict(width=3, dash="dash"),
                name=f"Berth reference {station}", showlegend=False,
                hoverinfo="skip",
            ))


def _add_reference_plane(fig: go.Figure, ship: dict, bollards: pd.DataFrame) -> None:
    if bollards.empty:
        return
    loa = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    offset = float(st.session_state.get("offset_fugro_m", 0.0))
    xmin = min(float(bollards.x_m.min()), offset - loa / 2.0) - 25.0
    xmax = max(float(bollards.x_m.max()), offset + loa / 2.0) + 25.0
    ymin = min(float(bollards.y_m.min()), -float(ship.get("Beam", DEFAULT_SHIP["Beam"])) / 2.0) - 25.0
    ymax = max(float(bollards.y_m.max()), float(ship.get("Beam", DEFAULT_SHIP["Beam"])) / 2.0) + 10.0
    fig.add_trace(go.Mesh3d(
        x=[xmin, xmax, xmax, xmin], y=[ymin, ymin, ymax, ymax], z=[0, 0, 0, 0],
        i=[0, 0], j=[1, 2], k=[2, 3], opacity=0.10,
        name="Survey reference plane", showlegend=False, hoverinfo="skip",
    ))


def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float) -> go.Figure:
    fig = go.Figure()
    _add_ship(fig, ship, offset)
    _add_fixed_berth(fig, bollards)
    _add_reference_plane(fig, ship, bollards)

    fig.update_layout(
        height=760,
        margin=dict(l=0, r=0, t=25, b=0),
        scene=dict(
            xaxis_title="X — Longitudinale (+ PRUA) [m]",
            yaxis_title="Y — Trasversale (+ PORT) [m]",
            zaxis_title="Z — Quota [m]",
            aspectmode="auto",
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.05)),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    return fig


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")
    for key, value in DEFAULT_SHIP.items():
        ship_dict.setdefault(key, value)

    offset = float(st.session_state.get("offset_fugro_m", 0.0))
    df, survey_level = _profile_dataframe(selected_port)
    is_real_profile = selected_port in list_berth_profiles() and not df.empty

    if is_real_profile:
        st.success("✅ Ensenada Pier #2: rilievo reale attivo — 12 bitte sul lato PORT (sinistra)")
        st.caption(
            f"Riferimento rilievo: acqua +{survey_level:.2f} m. "
            "Le bitte sono fisse; soltanto la nave può traslare longitudinalmente."
        )
    else:
        st.info("Nessun profilo di rilievo fisso disponibile per questa banchina.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Nave", ship_dict.get("Name", "N/A"))
    c2.metric("Offset longitudinale", f"{offset:+.1f} m")
    c3.metric("Bitte nel rilievo", str(len(df)))

    new_offset = st.number_input(
        "Spostamento longitudinale nave — + PRUA / − POPPA (m)",
        value=offset, step=0.5, format="%.1f", key="berth_longitudinal_offset",
    )
    st.session_state["offset_fugro_m"] = float(new_offset)

    if not df.empty:
        st.subheader("🚢 Modello 3D originale Carnival Panorama + banchina + bitte")
        try:
            fig = _figure_3d(ship_dict, df, float(new_offset))
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
        except Exception as exc:
            st.error(f"⚠️ Impossibile caricare il modello 3D originale: {exc}")
            st.info(f"Percorso previsto del GLB: {GLB_MODEL_PATH}")

        with st.expander("📐 Dati delle bitte del rilievo", expanded=False):
            cols = [c for c in ["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"] if c in df.columns]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)

        st.caption(
            "Sistema 3D: X positivo verso prua; Y positivo verso PORT. "
            "Le bitte non seguono l'offset della nave. Il livello +0.20 m è il riferimento del rilievo e non viene sommato al draft."
        )
    else:
        st.warning("Nessuna geometria di banchina disponibile per questo porto.")
