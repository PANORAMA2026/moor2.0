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
    rows = [
        {
            "bollard_id": str(point.bollard_id),
            "measurement_station": str(point.measurement_station),
            "side": str(point.side),
            "x_m": float(point.x_m),
            "y_m": float(point.y_m),
            "z_m": float(point.z_m),
            "survey_water_level_m": float(point.survey_water_level_m),
        }
        for point in profile.get("points", ())
    ]
    df = pd.DataFrame.from_records(rows, columns=["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"])
    if profile_name == "Ensenada Pier #2" and len(df) != 12:
        raise ValueError(f"Ensenada Pier #2 survey integrity error: expected 12 bollards, got {len(df)}")
    return df, float(profile["survey_water_level_m"])


def _add_ship(fig: go.Figure, ship: dict, offset: float) -> tuple[float, float, float]:
    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")
    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, faces, _ = ship_mesh_to_plotly(mesh, ship, offset)
    fig.add_trace(go.Mesh3d(
        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color="gainsboro", flatshading=False, opacity=0.96,
        name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip",
    ))
    return float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1])), float(np.ptp(vertices[:, 2]))


def _add_platforms(fig: go.Figure, ship_offset: float) -> None:
    for station, p in get_mooring_platforms().items():
        x = float(p["x_m"]) + ship_offset
        y = float(p["y_m"])
        z = float(p["z_m"])
        deck = int(p["deck"])
        note = "27 m aft of extreme bow" if station == "FWD" else "14 m forward of extreme stern"
        fig.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z], mode="markers+text",
            text=[f"{station} MOORING PLATFORM — Deck {deck}"], textposition="top center",
            marker=dict(size=9, symbol="cross"), name=f"{station} mooring platform",
            showlegend=False,
            hovertemplate=f"{station} mooring platform — Deck {deck}<br>{note}<br>X=%{{x:.2f}} m<br>Y=%{{y:.2f}} m<br>Z=%{{z:.2f}} m<extra></extra>",
        ))


def _add_fairleads(fig: go.Figure, ship_offset: float, station_filter: str = "ALL") -> pd.DataFrame:
    points = get_fairleads(side="PORT")
    if station_filter != "ALL":
        points = tuple(p for p in points if p.station == station_filter)
    if not points:
        return pd.DataFrame()
    df = pd.DataFrame([p.__dict__ for p in points])
    x = df["x_m"].astype(float) + float(ship_offset)
    y = df["y_m"].astype(float)
    z = df["z_m"].astype(float)
    labels = [f"{r.point_id} — item {r.equipment_item}" for r in points]
    custom = np.column_stack([df["station"], df["deck"], df["frame_ref"], df["confidence"], df["source"]])
    fig.add_trace(go.Scatter3d(
        x=x.tolist(), y=y.tolist(), z=z.tolist(), mode="markers+text",
        text=df["point_id"].tolist(), textposition="top center",
        marker=dict(size=7, symbol="circle"), name="Fairleads — PORT",
        customdata=custom,
        hovertemplate=(
            "%{text}<br>Station=%{customdata[0]} — Deck %{customdata[1]}<br>"
            "Frame=%{customdata[2]}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<br>"
            "Geometry=%{customdata[3]}<extra></extra>"
        ),
    ))
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
    fig.add_trace(go.Mesh3d(
        x=xs, y=ys, z=zs, i=i, j=j, k=k,
        color="#3A8F5B", opacity=0.58, flatshading=False,
        lighting=dict(ambient=0.35, diffuse=0.80, specular=0.12, roughness=0.85),
        lightposition=dict(x=100, y=-100, z=200),
        name=f"{profile_name} — 3D berth solid",
        hovertemplate="Berth 3D solid<br>Top=%{z:.2f} m<extra></extra>",
    ))


def _add_fixed_berth(fig: go.Figure, bollards: pd.DataFrame) -> None:
    if bollards.empty:
        return
    x = pd.to_numeric(bollards["x_m"], errors="coerce")
    y = pd.to_numeric(bollards["y_m"], errors="coerce")
    z = pd.to_numeric(bollards["z_m"], errors="coerce")
    labels = [f"{r['measurement_station']} — {r['bollard_id']} — {r['side']}" for _, r in bollards.iterrows()]
    fig.add_trace(go.Scatter3d(
        x=x.tolist(), y=y.tolist(), z=z.tolist(), mode="markers+text",
        text=bollards["bollard_id"].astype(str).tolist(), textposition="top center",
        customdata=labels, marker=dict(size=9, symbol="diamond"),
        name="Ensenada Pier #2 — PORT Bollards",
        hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>",
    ))


def _connection_dataframe(bollards: pd.DataFrame, ship_offset: float) -> tuple[pd.DataFrame, list[str]]:
    fairleads = {p.point_id: p for p in get_fairleads(side="PORT")}
    bollard_rows = {}
    for _, row in bollards.iterrows():
        key = (str(row["measurement_station"]).upper(), str(row["bollard_id"]).upper())
        bollard_rows[key] = row

    records = []
    unresolved = []
    for conn in get_normal_setup():
        fairlead = fairleads.get(conn.fairlead_id)
        bollard = bollard_rows.get((conn.bollard_station.upper(), conn.bollard_id.upper()))
        if fairlead is None or bollard is None:
            unresolved.append(conn.line_id)
            continue
        fx = float(fairlead.x_m) + float(ship_offset)
        fy = float(fairlead.y_m)
        fz = float(fairlead.z_m)
        bx = float(bollard["x_m"])
        by = float(bollard["y_m"])
        bz = float(bollard["z_m"])
        length = float(np.linalg.norm(np.array([bx - fx, by - fy, bz - fz])))
        records.append({
            "line_id": conn.line_id,
            "station": conn.station,
            "line_type": conn.line_type,
            "fairlead_id": conn.fairlead_id,
            "bollard_id": conn.bollard_id,
            "fairlead_x_m": fx,
            "fairlead_y_m": fy,
            "fairlead_z_m": fz,
            "bollard_x_m": bx,
            "bollard_y_m": by,
            "bollard_z_m": bz,
            "straight_3d_length_m": length,
            "status": conn.status,
        })
    return pd.DataFrame.from_records(records), unresolved


def _add_mooring_connections(fig: go.Figure, connections: pd.DataFrame) -> None:
    line_style = {
        "HEAD": {"color": "#E6B800", "width": 5},
        "SPRING": {"color": "#FF7F0E", "width": 5},
        "STERN": {"color": "#1F77B4", "width": 5},
    }
    shown = set()
    for _, row in connections.iterrows():
        kind = str(row["line_type"])
        style = line_style.get(kind, {"color": "#777777", "width": 4})
        showlegend = kind not in shown
        shown.add(kind)
        fig.add_trace(go.Scatter3d(
            x=[row["fairlead_x_m"], row["bollard_x_m"]],
            y=[row["fairlead_y_m"], row["bollard_y_m"]],
            z=[row["fairlead_z_m"], row["bollard_z_m"]],
            mode="lines",
            line=style,
            name=f"{kind} lines" if showlegend else kind,
            legendgroup=kind,
            showlegend=showlegend,
            hovertemplate=(
                f"{row['line_id']} — {kind}<br>"
                f"Fairlead: {row['fairlead_id']}<br>"
                f"Bollard: {row['bollard_id']} ({row['station']})<br>"
                f"3D straight length: {row['straight_3d_length_m']:.1f} m<extra></extra>"
            ),
        ))


def _add_berth_reference_lines(fig: go.Figure, bollards: pd.DataFrame) -> None:
    for station in ("FWD", "AFT"):
        part = bollards[bollards["measurement_station"].astype(str).str.upper() == station].sort_values("x_m")
        if len(part) >= 2:
            fig.add_trace(go.Scatter3d(
                x=part["x_m"].tolist(), y=part["y_m"].tolist(), z=part["z_m"].tolist(),
                mode="lines", line=dict(width=3, dash="dash"), showlegend=False, hoverinfo="skip",
                name=f"Berth reference {station}",
            ))


def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float, fairlead_station: str) -> tuple[go.Figure, tuple[float, float, float], pd.DataFrame]:
    fig = go.Figure()
    model_dims = _add_ship(fig, ship, offset)
    _add_platforms(fig, offset)
    fairlead_df = _add_fairleads(fig, offset, fairlead_station)
    connections, unresolved = _connection_dataframe(bollards, offset)
    _add_mooring_connections(fig, connections)
    _add_berth_block(fig, bollards, "Ensenada Pier #2")
    _add_fixed_berth(fig, bollards)
    _add_berth_reference_lines(fig, bollards)
    fig.update_layout(
        height=820,
        margin=dict(l=0, r=0, t=25, b=0),
        scene=dict(
            xaxis_title="X — Longitudinale (+ PRUA) [m]",
            yaxis_title="Y — Trasversale (+ PORT) [m]",
            zaxis_title="Z — Quota [m]",
            aspectmode="data",
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.05)),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    return fig, model_dims, fairlead_df


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")
    for key, value in DEFAULT_SHIP.items():
        ship_dict.setdefault(key, value)

    offset = float(st.session_state.get("offset_fugro_m", 0.0))
    df, survey_level = _profile_dataframe(selected_port)
    normalized = str(selected_port).strip().lower()
    is_ensenada = normalized in {"ens", "ensenada", "ensenada pier #2", "ensenada pier 2"} or normalized.startswith("ensenada")

    if not is_ensenada:
        st.info("ℹ️ Nessun profilo di rilievo fisso disponibile per questa banchina.")
        return

    st.success("✅ Ensenada Pier #2 — RILIEVO REALE: 12 BITTE PORT (SINISTRA)")
    st.caption(
        f"Rilievo a livello acqua +{survey_level:.2f} m. FWD platform: Deck 3, 27 m a poppavia dell'estrema prua. "
        "AFT platform: Deck 1, 14 m a pruavia dell'estrema poppa. Le bitte sono fisse; la nave e gli elementi di bordo traslano longitudinalmente."
    )

    counts = setup_counts()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Nave", ship_dict.get("Name", "N/A"))
    c2.metric("Offset longitudinale", f"{offset:+.1f} m")
    c3.metric("Bitte nel rilievo", str(len(df)))
    c4.metric("Fairlead PORT", str(len(get_fairleads(side="PORT"))))
    c5.metric("Cime normal setup", str(counts["TOTAL"]))

    new_offset = st.number_input(
        "Spostamento longitudinale nave — + PRUA / − POPPA (m)",
        value=offset, step=0.5, format="%.1f", key="berth_longitudinal_offset",
    )
    st.session_state["offset_fugro_m"] = float(new_offset)

    station = st.selectbox("Fairleads da visualizzare", ["ALL", "FWD", "AFT"], format_func=lambda x: "Tutti" if x == "ALL" else x)
    st.subheader("🚢 Carnival Panorama — modello 3D + fairleads + 18 cime + banchina 3D + 12 bitte")

    try:
        fig, model_dims, fairlead_df = _figure_3d(ship_dict, df, float(new_offset), station)
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
        d1, d2, d3 = st.columns(3)
        d1.metric("Modello LOA", f"{model_dims[0]:.1f} m")
        d2.metric("Modello Beam", f"{model_dims[1]:.1f} m")
        d3.metric("Keel → Mast", f"{model_dims[2]:.1f} m")
    except Exception as exc:
        st.error(f"⚠️ Impossibile caricare il modello 3D originale: {exc}")
        st.info(f"Percorso previsto del GLB: {GLB_MODEL_PATH}")
        return

    st.caption(
        "Le 18 connessioni sono la topologia del normal setup Ensenada fornita dall'equipaggio. "
        "I fairlead sono ancora geometria REFERENCE derivata dal disegno; le linee mostrano quindi la connessione geometrica "
        "attuale e la loro lunghezza rettilinea 3D, non una lunghezza reale sotto sag/pretensionamento."
    )

    with st.expander("⚓ Normal Mooring Setup — Ensenada Pier #2", expanded=True):
        connections, unresolved = _connection_dataframe(df, float(new_offset))
        if unresolved:
            st.warning(f"Connessioni non risolte: {', '.join(unresolved)}")
        if not connections.empty:
            cols = ["line_id", "station", "line_type", "fairlead_id", "bollard_id", "straight_3d_length_m", "status"]
            st.dataframe(connections[cols], use_container_width=True, hide_index=True)
            fwd = int((connections["station"] == "FWD").sum())
            aft = int((connections["station"] == "AFT").sum())
            st.write(f"**FWD:** {fwd} cime — **AFT:** {aft} cime — **Totale:** {len(connections)} cime")

    with st.expander("📐 Coordinate fairleads — reference geometry", expanded=False):
        if fairlead_df.empty:
            st.warning("Nessun fairlead disponibile per il filtro selezionato.")
        else:
            cols = ["point_id", "station", "deck", "equipment_item", "side", "frame_ref", "x_m", "y_m", "z_m", "confidence"]
            st.dataframe(fairlead_df[cols].sort_values(["station", "x_m"]), use_container_width=True, hide_index=True)

    st.info(
        "Passo successivo: validare visivamente i fairlead/chock del disegno e poi sostituire i collegamenti REFERENCE con i punti "
        "engineering-grade. Dopo questa validazione potremo aggiungere winch → fairlead → linea → bitta e rendere ogni collegamento modificabile."
    )
