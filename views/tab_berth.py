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

def _profile_dataframe(selected_port: str):
    normalized = str(selected_port).strip().lower()
    aliases = {"ens": "Ensenada Pier #2", "ensenada": "Ensenada Pier #2", "ensenada pier #2": "Ensenada Pier #2", "ensenada pier 2": "Ensenada Pier #2"}
    profile_name = aliases.get(normalized, str(selected_port).strip())
    if profile_name not in list_berth_profiles():
        return pd.DataFrame(), None
    profile = get_berth_profile(profile_name)
    rows = [{"bollard_id": str(p.bollard_id), "measurement_station": str(p.measurement_station), "side": str(p.side), "x_m": float(p.x_m), "y_m": float(p.y_m), "z_m": float(p.z_m), "survey_water_level_m": float(p.survey_water_level_m)} for p in profile.get("points", ())]
    df = pd.DataFrame.from_records(rows, columns=["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"])
    if profile_name == "Ensenada Pier #2" and len(df) != 12:
        raise ValueError(f"Ensenada Pier #2 survey integrity error: expected 12 bollards, got {len(df)}")
    return df, float(profile["survey_water_level_m"])

def _add_ship(fig, ship, offset):
    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")
    vertices, faces, _ = ship_mesh_to_plotly(load_ship_glb(str(GLB_MODEL_PATH)), ship, offset)
    fig.add_trace(go.Mesh3d(x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2], i=faces[:, 0], j=faces[:, 1], k=faces[:, 2], color="gainsboro", flatshading=False, opacity=0.96, name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip"))
    return float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1])), float(np.ptp(vertices[:, 2]))

def _add_platforms(fig, ship_offset):
    for station, p in get_mooring_platforms().items():
        x, y, z = float(p["x_m"]) + ship_offset, float(p["y_m"]), float(p["z_m"])
        deck = int(p["deck"])
        note = "27 m aft of extreme bow" if station == "FWD" else "14 m forward of extreme stern"
        fig.add_trace(go.Scatter3d(x=[x], y=[y], z=[z], mode="markers+text", text=[f"{station} MOORING PLATFORM — Deck {deck}"], textposition="top center", marker=dict(size=9, symbol="cross"), name=f"{station} mooring platform", showlegend=False, hovertemplate=f"{station} mooring platform — Deck {deck}<br>{note}<br>X=%{{x:.2f}} m<br>Y=%{{y:.2f}} m<br>Z=%{{z:.2f}} m<extra></extra>"))

def _add_fairleads(fig, ship_offset, station_filter="ALL"):
    points = get_fairleads(side="PORT")
    if station_filter != "ALL":
        points = tuple(p for p in points if p.station == station_filter)
    if not points:
        return pd.DataFrame()
    df = pd.DataFrame([p.__dict__ for p in points])
    x, y, z = df["x_m"].astype(float) + float(ship_offset), df["y_m"].astype(float), df["z_m"].astype(float)
    custom = np.column_stack([df["station"], df["deck"], df["frame_ref"], df["confidence"]])
    fig.add_trace(go.Scatter3d(x=x.tolist(), y=y.tolist(), z=z.tolist(), mode="markers+text", text=df["point_id"].tolist(), textposition="top center", marker=dict(size=7, symbol="circle"), name="Fairleads — PORT", customdata=custom, hovertemplate="%{text}<br>Station=%{customdata[0]} — Deck %{customdata[1]}<br>Frame=%{customdata[2]}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<br>Geometry=%{customdata[3]}<extra></extra>"))
    return df

def _add_berth_block(fig, bollards, profile_name):
    if bollards.empty:
        return
    profile = get_berth_profile(profile_name)
    platform_y = float(profile["platforms"]["FWD"]["y_m"])
    xmin, xmax = float(bollards["x_m"].min()) - BERTH_BLOCK_MARGIN_X_M, float(bollards["x_m"].max()) + BERTH_BLOCK_MARGIN_X_M
    ymin, ymax = platform_y - 4.0, float(bollards["y_m"].max()) + BERTH_BLOCK_MARGIN_Y_M
    top_z, bottom_z = float(bollards["z_m"].median()), float(bollards["z_m"].median()) - BERTH_BLOCK_DEPTH_M
    xs = [xmin, xmax, xmax, xmin, xmin, xmax, xmax, xmin]; ys = [ymin, ymin, ymax, ymax, ymin, ymin, ymax, ymax]; zs = [top_z, top_z, top_z, top_z, bottom_z, bottom_z, bottom_z, bottom_z]
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3]; j = [1, 2, 5, 6, 4, 5, 2, 6, 3, 7, 0, 4]; k = [2, 3, 6, 7, 5, 1, 6, 5, 7, 6, 4, 7]
    fig.add_trace(go.Mesh3d(x=xs, y=ys, z=zs, i=i, j=j, k=k, color="#3A8F5B", opacity=0.58, flatshading=False, name=f"{profile_name} — 3D berth solid", hovertemplate="Berth 3D solid<br>Top=%{z:.2f} m<extra></extra>"))

def _add_fixed_berth(fig, bollards):
    if bollards.empty:
        return
    labels = [f"{r['measurement_station']} — {r['bollard_id']} — {r['side']}" for _, r in bollards.iterrows()]
    fig.add_trace(go.Scatter3d(x=pd.to_numeric(bollards["x_m"]).tolist(), y=pd.to_numeric(bollards["y_m"]).tolist(), z=pd.to_numeric(bollards["z_m"]).tolist(), mode="markers+text", text=bollards["bollard_id"].astype(str).tolist(), textposition="top center", customdata=labels, marker=dict(size=9, symbol="diamond"), name="Ensenada Pier #2 — PORT Bollards", hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>"))

def _connection_dataframe(bollards, ship_offset):
    fairleads = {p.point_id: p for p in get_fairleads(side="PORT")}
    bollard_rows = {(str(r["measurement_station"]).upper(), str(r["bollard_id"]).upper()): r for _, r in bollards.iterrows()}
    records, unresolved = [], []
    for conn in get_normal_setup():
        fairlead = fairleads.get(conn.fairlead_id); bollard = bollard_rows.get((conn.bollard_station.upper(), conn.bollard_id.upper()))
        if fairlead is None or bollard is None:
            unresolved.append(conn.line_id); continue
        fx, fy, fz = float(fairlead.x_m) + float(ship_offset), float(fairlead.y_m), float(fairlead.z_m)
        bx, by, bz = float(bollard["x_m"]), float(bollard["y_m"]), float(bollard["z_m"])
        length = float(np.linalg.norm(np.array([bx - fx, by - fy, bz - fz])))
        records.append({"line_id": conn.line_id, "station": conn.station, "line_type": conn.line_type, "fairlead_id": conn.fairlead_id, "bollard_id": conn.bollard_id, "fairlead_x_m": fx, "fairlead_y_m": fy, "fairlead_z_m": fz, "bollard_x_m": bx, "bollard_y_m": by, "bollard_z_m": bz, "straight_3d_length_m": length, "status": conn.status})
    return pd.DataFrame.from_records(records), unresolved

def _add_mooring_connections(fig, connections):
    styles = {"HEAD": {"color": "#E6B800", "width": 5}, "SPRING": {"color": "#FF7F0E", "width": 5}, "STERN": {"color": "#1F77B4", "width": 5}}
    shown = set()
    for _, row in connections.iterrows():
        kind = str(row["line_type"]); showlegend = kind not in shown; shown.add(kind)
        fig.add_trace(go.Scatter3d(x=[row["fairlead_x_m"], row["bollard_x_m"]], y=[row["fairlead_y_m"], row["bollard_y_m"]], z=[row["fairlead_z_m"], row["bollard_z_m"]], mode="lines", line=styles.get(kind, {"color": "#777777", "width": 4}), name=f"{kind} lines" if showlegend else kind, legendgroup=kind, showlegend=showlegend, hovertemplate=f"{row['line_id']} — {kind}<br>Fairlead: {row['fairlead_id']}<br>Bollard: {row['bollard_id']} ({row['station']})<br>3D straight length: {row['straight_3d_length_m']:.1f} m<extra></extra>"))

def _add_berth_reference_lines(fig, bollards):
    for station in ("FWD", "AFT"):
        part = bollards[bollards["measurement_station"].astype(str).str.upper() == station].sort_values("x_m")
        if len(part) >= 2:
            fig.add_trace(go.Scatter3d(x=part["x_m"].tolist(), y=part["y_m"].tolist(), z=part["z_m"].tolist(), mode="lines", line=dict(width=3, dash="dash"), showlegend=False, hoverinfo="skip"))

def _figure_3d(ship, bollards, offset, fairlead_station):
    fig = go.Figure()
    model_dims = _add_ship(fig, ship, offset)
    _add_platforms(fig, offset)
    fairlead_df = _add_fairleads(fig, offset, fairlead_station)
    connections, unresolved = _connection_dataframe(bollards, offset)
    _add_mooring_connections(fig, connections)
    _add_berth_block(fig, bollards, "Ensenada Pier #2")
    _add_fixed_berth(fig, bollards)
    _add_berth_reference_lines(fig, bollards)
    fig.update_layout(height=820, margin=dict(l=0, r=0, t=25, b=0), scene=dict(xaxis_title="X — Longitudinale (+ PRUA) [m]", yaxis_title="Y — Trasversale (+ PORT) [m]", zaxis_title="Z — Quota [m]", aspectmode="data"), legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0))
    return fig, fairlead_df, connections, unresolved, model_dims

def render_tab_berth(selected_port: str = "Ensenada Pier #2", ship: dict | None = None):
    """Render the 3D berth/layout tab used by app.py."""
    ship = ship or DEFAULT_SHIP
    st.subheader("🗺️ Layout Banchina & Bitte — Modello 3D")
    normalized = str(selected_port).strip().lower()
    aliases = {"ens": "Ensenada Pier #2", "ensenada": "Ensenada Pier #2", "ensenada pier #2": "Ensenada Pier #2", "ensenada pier 2": "Ensenada Pier #2"}
    profile_name = aliases.get(normalized, str(selected_port).strip())
    bollards, survey_level = _profile_dataframe(profile_name)
    if bollards.empty:
        st.warning(f"Nessun profilo banchina disponibile per: {selected_port}")
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        offset = st.number_input("Offset longitudinale nave (m)", value=0.0, step=0.5, key="berth_ship_offset_m")
    with c2:
        fairlead_station = st.selectbox("Fairleads visualizzati", ["ALL", "FWD", "AFT"], key="berth_fairlead_station")
    with c3:
        counts = setup_counts(); st.metric("Connessioni setup Normal", int(sum(counts.values())))
    st.caption(f"Profilo banchina: **{profile_name}** · Survey water level: **+{survey_level:.2f} m** · Bollards: **{len(bollards)}**")
    st.info("Le coordinate dei fairlead derivano dal pianetto e sono ancora marcate REFERENCE. Non devono essere considerate solver-grade finché non vengono validate con misure a bordo.")
    try:
        fig, fairlead_df, connections, unresolved, model_dims = _figure_3d(ship, bollards, float(offset), fairlead_station)
        st.plotly_chart(fig, use_container_width=True, key="berth_layout_3d")
    except Exception as exc:
        st.error(f"Errore nella costruzione del modello 3D: {exc}")
        return
    if unresolved:
        st.warning("Connessioni non risolte: " + ", ".join(unresolved))
    with st.expander("🔗 Connessioni Winch/Fairlead → Bollard", expanded=False):
        st.dataframe(connections, use_container_width=True, hide_index=True) if not connections.empty else st.warning("Nessuna connessione risolta.")
    with st.expander("📍 Coordinate fairlead — riferimento da disegno", expanded=False):
        if fairlead_df.empty: st.info("Nessun fairlead disponibile per il filtro selezionato.")
        else:
            cols = [c for c in ["point_id", "station", "deck", "equipment_item", "frame_ref", "x_m", "y_m", "z_m", "confidence", "source"] if c in fairlead_df.columns]
            st.dataframe(fairlead_df[cols], use_container_width=True, hide_index=True)
    with st.expander("⚓ Coordinate bitte rilevate", expanded=False):
        st.dataframe(bollards, use_container_width=True, hide_index=True)
    with st.expander("📐 Modello e convenzioni", expanded=False):
        st.write({"GLB_path": str(GLB_MODEL_PATH), "GLB_calibrated_dimensions_m": {"LOA": round(model_dims[0], 2), "Beam": round(model_dims[1], 2), "Height": round(model_dims[2], 2)}, "ship_runtime_offset": float(offset), "ship_transverse_offset": 0.0, "ship_heading_offset_deg": 0.0, "berth_fixed": True, "coordinate_system": "+X bow / +Y PORT / +Z upward"})
