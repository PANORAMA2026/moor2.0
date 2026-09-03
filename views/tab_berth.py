"""3D berth layout: Carnival Panorama + surveyed berth + drawing-derived fairleads + lines."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import trimesh

from config.constants import DEFAULT_SHIP
from core.berth_profiles import get_berth_profile, list_berth_profiles
from core.mooring_equipment import get_fairleads, get_mooring_platforms
from core.mooring_setup_profiles import get_normal_setup, setup_counts

GLB_MODEL_PATH = Path(__file__).resolve().parent.parent / "asset" / "carnivalpanorama.glb"
BERTH_BLOCK_DEPTH_M = 15.0
BERTH_BLOCK_MARGIN_X_M = 20.0
BERTH_BLOCK_MARGIN_Y_M = 8.0


@st.cache_resource(show_spinner=False)
def load_ship_glb(path: str):
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        geometries = [g.copy() for g in loaded.geometry.values()]
        if not geometries:
            raise ValueError("The GLB scene contains no geometry")
        return trimesh.util.concatenate(geometries)
    return loaded


def ship_mesh_to_plotly(mesh, ship: dict, offset_x: float = 0.0):
    vertices = np.asarray(mesh.vertices, dtype=float).copy()
    faces = np.asarray(mesh.faces, dtype=int)
    if vertices.size == 0 or faces.size == 0:
        raise ValueError("Empty ship mesh")
    raw_extents = np.ptp(vertices, axis=0)
    if np.any(raw_extents <= 0):
        raise ValueError(f"Invalid GLB dimensions: {raw_extents.tolist()}")

    order = np.argsort(raw_extents)[::-1]
    length_axis, height_axis, width_axis = int(order[0]), int(order[1]), int(order[2])
    aligned = np.zeros_like(vertices)
    aligned[:, 0] = -vertices[:, length_axis]
    aligned[:, 1] = vertices[:, width_axis]
    aligned[:, 2] = vertices[:, height_axis]
    aligned[:, 0] -= (aligned[:, 0].min() + aligned[:, 0].max()) / 2.0
    aligned[:, 1] -= (aligned[:, 1].min() + aligned[:, 1].max()) / 2.0
    aligned[:, 2] -= aligned[:, 2].min()

    loa_m = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    beam_m = float(ship.get("Beam", DEFAULT_SHIP["Beam"]))
    draft_m = float(ship.get("Draft", DEFAULT_SHIP["Draft"]))
    air_draft_m = float(ship.get("Air_Draft_Mast", 0.0))
    target_height_m = draft_m + air_draft_m if air_draft_m > 0 else loa_m
    aligned[:, 0] *= loa_m / raw_extents[length_axis]
    aligned[:, 1] *= beam_m / raw_extents[width_axis]
    aligned[:, 2] *= target_height_m / raw_extents[height_axis]
    aligned[:, 0] += float(offset_x)
    aligned[:, 2] -= draft_m
    return aligned, faces, raw_extents


def _profile_dataframe(selected_port: str) -> tuple[pd.DataFrame, float | None]:
    normalized = str(selected_port).strip().lower()
    aliases = {
        "ens": "Ensenada Pier #2",
        "ensenada": "Ensenada Pier #2",
        "ensenada pier #2": "Ensenada Pier #2",
        "ensenada pier 2": "Ensenada Pier #2",
    }
    profile_name = aliases.get(normalized, str(selected_port).strip())
    if profile_name not in list_berth_profiles():
        return pd.DataFrame(), None
    profile = get_berth_profile(profile_name)
    rows = [{"bollard_id": str(point.bollard_id), "measurement_station": str(point.measurement_station), "side": str(point.side), "x_m": float(point.x_m), "y_m": float(point.y_m), "z_m": float(point.z_m), "survey_water_level_m": float(point.survey_water_level_m)} for point in profile.get("points", ())]
    df = pd.DataFrame.from_records(rows, columns=["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"])
    if profile_name == "Ensenada Pier #2" and len(df) != 12:
        raise ValueError(f"Ensenada Pier #2 survey integrity error: expected 12 bollards, got {len(df)}")
    return df, float(profile["survey_water_level_m"])


def _add_ship(fig: go.Figure, ship: dict, offset: float) -> tuple[float, float, float]:
    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")
    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, faces, _ = ship_mesh_to_plotly(mesh, ship, offset)
    fig.add_trace(go.Mesh3d(x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2], i=faces[:, 0], j=faces[:, 1], k=faces[:, 2], color="gainsboro", flatshading=False, opacity=0.96, name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip"))
    return float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1])), float(np.ptp(vertices[:, 2]))


def _ship_port_surface_y(vertices: np.ndarray, x_target: float, z_target: float) -> float:
    """Return the outer PORT hull Y at a longitudinal/elevation station.

    The calibrated GLB is the geometric source. We sample a narrow X/Z window and
    take the maximum Y, which follows the hull flare instead of assuming constant beam/2.
    """
    x = vertices[:, 0]
    y = vertices[:, 1]
    z = vertices[:, 2]
    x_tol = max(0.8, float(np.ptp(x)) * 0.0025)
    z_tol = 1.5
    mask = (np.abs(x - x_target) <= x_tol) & (np.abs(z - z_target) <= z_tol)
    if not np.any(mask):
        mask = np.abs(x - x_target) <= max(1.5, float(np.ptp(x)) * 0.006)
    if not np.any(mask):
        return float(np.interp(x_target, [x.min(), x.max()], [0.0, 0.0]))
    return float(np.max(y[mask]))


def _fairlead_dataframe(ship: dict, ship_offset: float) -> pd.DataFrame:
    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, _, _ = ship_mesh_to_plotly(mesh, ship, ship_offset)
    records = []
    for p in get_fairleads(side="PORT"):
        x = float(p.x_m) + float(ship_offset)
        z = float(p.z_m)
        y = _ship_port_surface_y(vertices, x, z)
        records.append({**p.__dict__, "x_m": x, "y_m": y, "z_m": z})
    return pd.DataFrame.from_records(records)


def _add_platforms(fig: go.Figure, ship_offset: float) -> None:
    for station, p in get_mooring_platforms().items():
        x = float(p["x_m"]) + ship_offset
        y = 0.0
        z = float(p["z_m"])
        deck = int(p["deck"])
        note = "27 m aft of extreme bow" if station == "FWD" else "14 m forward of extreme stern"
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[z], mode="markers+text", text=[f"{station} MOORING PLATFORM — Deck {deck}"], textposition="top center", marker=dict(size=9, symbol="cross"), name=f"{station} mooring platform", showlegend=False, hovertemplate=f"{station} mooring platform — Deck {deck}<br>{note}<br>X=%{{x:.2f}} m<br>Y=%{{y:.2f}} m<br>Z=%{{z:.2f}} m<extra></extra>"))


def _add_fairleads(fig: go.Figure, ship: dict, ship_offset: float, station_filter: str = "ALL") -> pd.DataFrame:
    df = _fairlead_dataframe(ship, ship_offset)
    if station_filter != "ALL":
        df = df[df["station"].astype(str) == station_filter].copy()
    if df.empty:
        return df
    custom = np.column_stack([df["station"], df["deck"], df["frame_ref"], df["confidence"], df["source"]])
    fig.add_trace(go.Scatter3d(x=df["x_m"].tolist(), y=df["y_m"].tolist(), z=df["z_m"].tolist(), mode="markers+text", text=df["point_id"].tolist(), textposition="top center", marker=dict(size=7, symbol="circle"), name="Fairleads — PORT", customdata=custom, hovertemplate="%{text}<br>Station=%{customdata[0]} — Deck %{customdata[1]}<br>Frame=%{customdata[2]}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>"))
    return df


def _add_berth_block(fig: go.Figure, bollards: pd.DataFrame, profile_name: str) -> None:
    if bollards.empty:
        return
    profile = get_berth_profile(profile_name)
    platform_y = float(profile["platforms"]["FWD"]["y_m"])
    xmin = float(bollards["x_m"].min()) - BERTH_BLOCK_MARGIN_X_M
    xmax = float(bollards["x_m"].max()) + BERTH_BLOCK_MARGIN_X_M
    ymin = platform_y - 4.0
    ymax = float(bollards["y_m"].max()) + BERTH_BLOCK_MARGIN_Y_M
    top_z = float(bollards["z_m"].median())
    bottom_z = top_z - BERTH_BLOCK_DEPTH_M
    xs = [xmin, xmax, xmax, xmin, xmin, xmax, xmax, xmin]
    ys = [ymin, ymin, ymax, ymax, ymin, ymin, ymax, ymax]
    zs = [top_z, top_z, top_z, top_z, bottom_z, bottom_z, bottom_z, bottom_z]
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]
    j = [1, 2, 5, 6, 4, 5, 2, 6, 3, 7, 0, 4]
    k = [2, 3, 6, 7, 5, 1, 6, 5, 7, 6, 4, 7]
    fig.add_trace(go.Mesh3d(x=xs, y=ys, z=zs, i=i, j=j, k=k, color="#3A8F5B", opacity=0.58, flatshading=False, lighting=dict(ambient=0.35, diffuse=0.80, specular=0.12, roughness=0.85), lightposition=dict(x=100, y=-100, z=200), name=f"{profile_name} — 3D berth solid", hovertemplate="Berth 3D solid<br>Top=%{z:.2f} m<extra></extra>"))


def _add_fixed_berth(fig: go.Figure, bollards: pd.DataFrame) -> None:
    if bollards.empty:
        return
    x = pd.to_numeric(bollards["x_m"], errors="coerce")
    y = pd.to_numeric(bollards["y_m"], errors="coerce")
    z = pd.to_numeric(bollards["z_m"], errors="coerce")
    labels = [f"{r['measurement_station']} — {r['bollard_id']} — {r['side']}" for _, r in bollards.iterrows()]
    fig.add_trace(go.Scatter3d(x=x.tolist(), y=y.tolist(), z=z.tolist(), mode="markers+text", text=bollards["bollard_id"].astype(str).tolist(), textposition="top center", customdata=labels, marker=dict(size=9, symbol="diamond"), name="Ensenada Pier #2 — PORT Bollards", hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>"))


def _connection_dataframe(bollards: pd.DataFrame, fairleads: pd.DataFrame, ship_offset: float) -> tuple[pd.DataFrame, list[str]]:
    fairlead_map = {str(r["point_id"]): r for _, r in fairleads.iterrows()}
    bollard_rows = {(str(row["measurement_station"]).upper(), str(row["bollard_id"]).upper()): row for _, row in bollards.iterrows()}
    records, unresolved = [], []
    for conn in get_normal_setup():
        fairlead = fairlead_map.get(conn.fairlead_id)
        bollard = bollard_rows.get((conn.bollard_station.upper(), conn.bollard_id.upper()))
        if fairlead is None or bollard is None:
            unresolved.append(conn.line_id); continue
        fx, fy, fz = float(fairlead["x_m"]), float(fairlead["y_m"]), float(fairlead["z_m"])
        bx, by, bz = float(bollard["x_m"]), float(bollard["y_m"]), float(bollard["z_m"])
        length = float(np.linalg.norm(np.array([bx-fx, by-fy, bz-fz])))
        records.append({"line_id": conn.line_id, "station": conn.station, "line_type": conn.line_type, "fairlead_id": conn.fairlead_id, "bollard_id": conn.bollard_id, "fairlead_x_m": fx, "fairlead_y_m": fy, "fairlead_z_m": fz, "bollard_x_m": bx, "bollard_y_m": by, "bollard_z_m": bz, "straight_3d_length_m": length, "status": conn.status})
    return pd.DataFrame.from_records(records), unresolved


def _add_mooring_connections(fig: go.Figure, connections: pd.DataFrame) -> None:
    line_style = {"HEAD": {"color": "#E6B800", "width": 5}, "SPRING": {"color": "#FF7F0E", "width": 5}, "STERN": {"color": "#1F77B4", "width": 5}}
    shown = set()
    for _, row in connections.iterrows():
        kind = str(row["line_type"]); style = line_style.get(kind, {"color": "#777777", "width": 4}); showlegend = kind not in shown; shown.add(kind)
        fig.add_trace(go.Scatter3d(x=[row["fairlead_x_m"], row["bollard_x_m"]], y=[row["fairlead_y_m"], row["bollard_y_m"]], z=[row["fairlead_z_m"], row["bollard_z_m"]], mode="lines", line=style, name=f"{kind} lines" if showlegend else kind, legendgroup=kind, showlegend=showlegend, hovertemplate=f"{row['line_id']} — {kind}<br>Fairlead: {row['fairlead_id']}<br>Bollard: {row['bollard_id']} ({row['station']})<br>3D straight length: {row['straight_3d_length_m']:.1f} m<extra></extra>"))


def _add_berth_reference_lines(fig: go.Figure, bollards: pd.DataFrame) -> None:
    for station in ("FWD", "AFT"):
        part = bollards[bollards["measurement_station"].astype(str).str.upper() == station].sort_values("x_m")
        if len(part) >= 2:
            fig.add_trace(go.Scatter3d(x=part["x_m"].tolist(), y=part["y_m"].tolist(), z=part["z_m"].tolist(), mode="lines", line=dict(width=3, dash="dash"), showlegend=False, hoverinfo="skip", name=f"Berth reference {station}"))


def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float, fairlead_station: str) -> tuple[go.Figure, tuple[float, float, float], pd.DataFrame]:
    fig = go.Figure()
    model_dims = _add_ship(fig, ship, offset)
    _add_platforms(fig, offset)
    fairleads = _add_fairleads(fig, ship, offset, fairlead_station)
    _add_fixed_berth(fig, bollards)
    profile_name = "Ensenada Pier #2" if not bollards.empty else "Berth"
    if not bollards.empty:
        _add_berth_block(fig, bollards, profile_name)
        _add_berth_reference_lines(fig, bollards)
    connections, unresolved = _connection_dataframe(bollards, fairleads if fairlead_station == "ALL" else _fairlead_dataframe(ship, offset), offset)
    if not connections.empty:
        _add_mooring_connections(fig, connections)
    return fig, model_dims, connections


def render_tab() -> None:
    st.subheader("3. Layout Banchina & Bitte")
    ports = list_berth_profiles()
    if not ports:
        st.warning("No berth profiles configured.")
        return
    selected_port = st.selectbox("Berth profile", ports, key="berth_profile_select")
    bollards, survey_level = _profile_dataframe(selected_port)
    ship_offset = st.slider("Ship longitudinal offset (m)", -50.0, 50.0, 0.0, 0.5, key="ship_longitudinal_offset")
    fairlead_station = st.radio("Fairleads", ["ALL", "FWD", "AFT"], horizontal=True, key="fairlead_station_filter")
    fig, dims, connections = _figure_3d(DEFAULT_SHIP, bollards, ship_offset, fairlead_station)
    fig.update_layout(height=760, margin=dict(l=0, r=0, t=40, b=0), scene=dict(aspectmode="data", xaxis_title="X — Longitudinal (+Bow)", yaxis_title="Y — Transverse (+Port)", zaxis_title="Z — Vertical", camera=dict(eye=dict(x=1.55, y=1.45, z=1.05))), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"GLB calibrated dimensions: LOA {dims[0]:.2f} m × Beam {dims[1]:.2f} m × Height {dims[2]:.2f} m. Fairlead transverse positions are projected onto the PORT hull surface from the GLB; longitudinal positions remain drawing/frame-derived references.")
    if survey_level is not None:
        st.caption(f"Berth survey reference water level: +{survey_level:.2f} m. Bollards are fixed; only ship longitudinal offset is movable in this model.")
    st.markdown("### Normal setup")
    counts = setup_counts()
    st.write(f"FWD: {counts['FWD']} lines — AFT: {counts['AFT']} lines — Total: {counts['TOTAL']} lines")
    if not connections.empty:
        with st.expander("Connection table", expanded=False):
            st.dataframe(connections, use_container_width=True, hide_index=True)
    with st.expander("Fairlead coordinates / geometry source", expanded=False):
        st.dataframe(_fairlead_dataframe(DEFAULT_SHIP, ship_offset), use_container_width=True, hide_index=True)
    st.info("Current fairlead positions are generated from the calibrated GLB hull surface at the drawing-derived longitudinal stations. They are geometric reference points and should be visually validated before being promoted to solver-grade survey geometry.")
