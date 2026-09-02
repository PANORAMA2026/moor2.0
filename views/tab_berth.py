"""3D berth layout: original Carnival Panorama GLB + fixed surveyed bollards.

The GLB is treated as the authoritative ship shape and size.  The application
may rotate/re-axis the mesh into the engineering coordinate system and translate
it, but it does NOT rescale, stretch, or compress the original model.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import trimesh
from config.constants import DEFAULT_SHIP
from core.berth_profiles import get_berth_profile, list_berth_profiles

GLB_MODEL_PATH = Path(__file__).resolve().parent.parent / "asset" / "carnivalpanorama.glb"

@st.cache_resource(show_spinner=False)
def load_ship_glb(path: str):
    loaded = trimesh.load(path, force="scene")
    if isinstance(loaded, trimesh.Scene):
        geometries = [g.copy() for g in loaded.geometry.values()]
        if not geometries:
            raise ValueError("The GLB scene contains no geometry")
        return trimesh.util.concatenate(geometries)
    return loaded

def ship_mesh_to_plotly(mesh, draft_m: float, offset_x: float = 0.0):
    """Map the original GLB into X/Y/Z without changing its dimensions.

    Only axis assignment, translation and the requested longitudinal offset are
    applied.  No scaling is performed: LOA/beam/height therefore remain the
    dimensions encoded in the original GLB.
    """
    vertices = np.asarray(mesh.vertices, dtype=float).copy()
    faces = np.asarray(mesh.faces, dtype=int)
    if vertices.size == 0 or faces.size == 0:
        raise ValueError("Empty ship mesh")

    extents = np.ptp(vertices, axis=0)
    if np.any(extents <= 0):
        raise ValueError(f"Invalid GLB dimensions: {extents.tolist()}")

    order = np.argsort(extents)[::-1]
    length_axis = int(order[0])
    width_axis = int(order[2])
    height_axis = int(order[1])

    aligned = np.zeros_like(vertices)
    # Preserve the original dimensions.  Reverse X only to match the
    # engineering convention +X = bow used by the berth survey.
    aligned[:, 0] = -vertices[:, length_axis]
    aligned[:, 1] = vertices[:, width_axis]
    aligned[:, 2] = vertices[:, height_axis]

    # Centre only by translation; never scale.
    aligned[:, 0] -= (aligned[:, 0].min() + aligned[:, 0].max()) / 2.0
    aligned[:, 0] += float(offset_x)
    aligned[:, 1] -= (aligned[:, 1].min() + aligned[:, 1].max()) / 2.0

    # Put the model's lowest point at -draft so z=0 is the water reference.
    # This changes position only, not vertical dimensions.
    aligned[:, 2] -= aligned[:, 2].min()
    aligned[:, 2] -= float(draft_m)
    return aligned, faces, extents, (length_axis, width_axis, height_axis)

def _profile_dataframe(selected_port: str) -> tuple[pd.DataFrame, float | None]:
    """Return authoritative fixed survey geometry for Ensenada.

    The legacy 5-bollard DB fallback is deliberately excluded from the 3D
    engineering view because it is not the onboard survey.
    """
    normalized = str(selected_port).strip().lower()
    aliases = {
        "ens": "Ensenada Pier #2",
        "ensenada": "Ensenada Pier #2",
        "ensenada pier #2": "Ensenada Pier #2",
        "ensenada pier 2": "Ensenada Pier #2",
    }
    profile_name = aliases.get(normalized)
    if profile_name is None:
        profile_name = "Ensenada Pier #2" if normalized.startswith("ensenada") else str(selected_port).strip()

    if profile_name not in list_berth_profiles():
        return pd.DataFrame(), None

    profile = get_berth_profile(profile_name)
    rows = []
    for point in profile.get("points", ()):
        rows.append({
            "bollard_id": str(point.bollard_id),
            "measurement_station": str(point.measurement_station),
            "side": str(point.side),
            "x_m": float(point.x_m),
            "y_m": float(point.y_m),
            "z_m": float(point.z_m),
            "survey_water_level_m": float(point.survey_water_level_m),
        })
    df = pd.DataFrame.from_records(rows, columns=[
        "bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"
    ])
    if profile_name == "Ensenada Pier #2" and len(df) != 12:
        raise ValueError(f"Ensenada Pier #2 survey integrity error: expected 12 bollards, got {len(df)}")
    return df, float(profile["survey_water_level_m"])

def _add_ship(fig: go.Figure, ship: dict, offset: float) -> tuple[float, float, float]:
    draft = float(ship.get("Draft", DEFAULT_SHIP["Draft"]))
    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")

    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, faces, raw_extents, axes = ship_mesh_to_plotly(mesh, draft, offset)
    fig.add_trace(go.Mesh3d(
        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color="gainsboro", flatshading=False, opacity=0.96,
        name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip"
    ))

    # These are reference points only; they are positioned from the configured
    # ship dimensions, while the GLB itself retains its own dimensions.
    loa_cfg = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    bridge_bow = float(ship.get("Bridge_To_Bow", DEFAULT_SHIP.get("Bridge_To_Bow", 39.5)))
    bridge_eye = float(ship.get("Bridge_Eye_Height", DEFAULT_SHIP.get("Bridge_Eye_Height", 26.4)))
    beam_max = float(ship.get("Beam_Max", DEFAULT_SHIP.get("Beam_Max", 49.4)))
    bridge_x = loa_cfg / 2.0 - bridge_bow + offset
    wing_y = beam_max / 2.0
    fig.add_trace(go.Scatter3d(
        x=[bridge_x, bridge_x], y=[-wing_y, wing_y], z=[bridge_eye, bridge_eye],
        mode="lines+markers", line=dict(width=5), marker=dict(size=3),
        name="Bridge Wings (reference)", hoverinfo="skip"
    ))
    model_dims = (float(np.ptp(vertices[:, 0])), float(np.ptp(vertices[:, 1])), float(np.ptp(vertices[:, 2])))
    return model_dims

def _add_platform_origins(fig: go.Figure, profile_name: str) -> None:
    profile = get_berth_profile(profile_name)
    platforms = profile.get("platforms", {})
    if not platforms:
        return
    for station in ("FWD", "AFT"):
        p = platforms.get(station)
        if not p:
            continue
        fig.add_trace(go.Scatter3d(
            x=[float(p["x_m"])], y=[float(p["y_m"])], z=[float(p["z_m"])],
            mode="markers+text", text=[f"{station} MOORING PLATFORM"],
            textposition="top center", marker=dict(size=7, symbol="cross"),
            name=f"{station} mooring platform", showlegend=False,
            hovertemplate=f"{station} mooring platform<br>X=%{{x:.2f}} m<br>Y=%{{y:.2f}} m<br>Z=%{{z:.2f}} m<extra></extra>"
        ))

def _add_fixed_berth(fig: go.Figure, bollards: pd.DataFrame) -> None:
    required = {"x_m", "y_m", "z_m", "bollard_id", "measurement_station", "side"}
    missing = sorted(required - set(bollards.columns))
    if bollards.empty or missing:
        raise ValueError(f"Bollard geometry missing columns: {missing}")
    x = pd.to_numeric(bollards["x_m"], errors="coerce")
    y = pd.to_numeric(bollards["y_m"], errors="coerce")
    z = pd.to_numeric(bollards["z_m"], errors="coerce")
    if x.isna().any() or y.isna().any() or z.isna().any():
        raise ValueError("Bollard geometry contains non-numeric coordinates")
    labels = [f"{r['measurement_station']} — {r['bollard_id']} — {r['side']}" for _, r in bollards.iterrows()]
    fig.add_trace(go.Scatter3d(
        x=x.tolist(), y=y.tolist(), z=z.tolist(), mode="markers+text",
        text=bollards["bollard_id"].astype(str).tolist(), textposition="top center",
        customdata=labels, marker=dict(size=9, symbol="diamond"),
        name="Ensenada Pier #2 — PORT Bollards",
        hovertemplate="%{customdata}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>"
    ))
    for station in ("FWD", "AFT"):
        part = bollards[bollards["measurement_station"].astype(str).str.upper() == station].sort_values("x_m")
        if len(part) >= 2:
            fig.add_trace(go.Scatter3d(
                x=part["x_m"].tolist(), y=part["y_m"].tolist(), z=part["z_m"].tolist(),
                mode="lines", line=dict(width=3, dash="dash"),
                name=f"Berth reference {station}", showlegend=False, hoverinfo="skip"
            ))

def _add_reference_plane(fig: go.Figure, ship: dict, bollards: pd.DataFrame, offset: float) -> None:
    if bollards.empty:
        return
    loa = float(ship.get("LOA", DEFAULT_SHIP["LOA"]))
    xmin = min(float(bollards["x_m"].min()), offset - loa / 2.0) - 25.0
    xmax = max(float(bollards["x_m"].max()), offset + loa / 2.0) + 25.0
    ymin = min(float(bollards["y_m"].min()), -float(ship.get("Beam", DEFAULT_SHIP["Beam"])) / 2.0) - 25.0
    ymax = max(float(bollards["y_m"].max()), float(ship.get("Beam", DEFAULT_SHIP["Beam"])) / 2.0) + 10.0
    fig.add_trace(go.Mesh3d(
        x=[xmin, xmax, xmax, xmin], y=[ymin, ymin, ymax, ymax], z=[0, 0, 0, 0],
        i=[0, 0], j=[1, 2], k=[2, 3], opacity=0.10,
        name="Survey reference plane", showlegend=False, hoverinfo="skip"
    ))

def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float) -> tuple[go.Figure, tuple[float, float, float]]:
    fig = go.Figure()
    model_dims = _add_ship(fig, ship, offset)
    _add_platform_origins(fig, "Ensenada Pier #2")
    _add_fixed_berth(fig, bollards)
    _add_reference_plane(fig, ship, bollards, offset)
    fig.update_layout(
        height=760,
        margin=dict(l=0, r=0, t=25, b=0),
        scene=dict(
            xaxis_title="X — Longitudinale (+ PRUA) [m]",
            yaxis_title="Y — Trasversale (+ PORT) [m]",
            zaxis_title="Z — Quota [m]",
            # Equal engineering scale on all axes: prevents the ship from
            # visually becoming a compressed/elongated 'box'.
            aspectmode="data",
            camera=dict(eye=dict(x=1.65, y=1.55, z=1.05)),
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
    )
    return fig, model_dims

def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")
    for key, value in DEFAULT_SHIP.items():
        ship_dict.setdefault(key, value)

    offset = float(st.session_state.get("offset_fugro_m", 0.0))
    df, survey_level = _profile_dataframe(selected_port)
    normalized = str(selected_port).strip().lower()
    is_real_profile = normalized in {"ens", "ensenada", "ensenada pier #2", "ensenada pier 2"} or normalized.startswith("ensenada")

    if is_real_profile:
        st.success("✅ Ensenada Pier #2 — RILIEVO REALE: 12 BITTE PORT (SINISTRA)")
        st.caption(
            f"Riferimento rilievo: livello acqua +{survey_level:.2f} m. "
            "Le distanze/azimut delle bitte sono misurati dalle FWD/AFT mooring platforms. "
            "Le bitte restano fisse; la nave trasla soltanto longitudinalmente."
        )
    else:
        st.info("ℹ️ Nessun profilo di rilievo fisso disponibile per questa banchina.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Nave", ship_dict.get("Name", "N/A"))
    c2.metric("Offset longitudinale", f"{offset:+.1f} m")
    c3.metric("Bitte nel rilievo", str(len(df)))

    new_offset = st.number_input(
        "Spostamento longitudinale nave — + PRUA / − POPPA (m)",
        value=offset, step=0.5, format="%.1f", key="berth_longitudinal_offset"
    )
    st.session_state["offset_fugro_m"] = float(new_offset)

    if is_real_profile:
        st.subheader("🚢 Carnival Panorama — modello 3D originale + banchina + bitte")
        try:
            fig, model_dims = _figure_3d(ship_dict, df, float(new_offset))
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
            d1, d2, d3 = st.columns(3)
            d1.metric("GLB LOA", f"{model_dims[0]:.1f} m")
            d2.metric("GLB Beam", f"{model_dims[1]:.1f} m")
            d3.metric("GLB Height", f"{model_dims[2]:.1f} m")
            st.caption("Le dimensioni sopra sono quelle del GLB originale: il modello non viene scalato dal software.")
        except Exception as exc:
            st.error(f"⚠️ Impossibile caricare il modello 3D originale: {exc}")
            st.info(f"Percorso previsto del GLB: {GLB_MODEL_PATH}")
        with st.expander("📐 Dati completi del rilievo", expanded=False):
            cols = ["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.caption("Per questo porto occorre inserire un rilievo reale di banchina prima di visualizzare bitte e collegamenti nel modello 3D.")
