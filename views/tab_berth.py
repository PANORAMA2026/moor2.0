"""3D berth layout: calibrated Carnival Panorama GLB + fixed surveyed berth."""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import trimesh
from PIL import Image
from config.constants import DEFAULT_SHIP
from core.berth_profiles import get_berth_profile, list_berth_profiles
from core.mooring_reference_images import get_mooring_plan_image
from core.mooring_reference_calibration import get_default_calibration, PlanCalibration

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
    """Calibrate the GLB to configured vessel dimensions, then translate only."""
    vertices = np.asarray(mesh.vertices, dtype=float).copy()
    faces = np.asarray(mesh.faces, dtype=int)
    if vertices.size == 0 or faces.size == 0:
        raise ValueError("Empty ship mesh")
    raw_extents = np.ptp(vertices, axis=0)
    if np.any(raw_extents <= 0):
        raise ValueError(f"Invalid GLB dimensions: {raw_extents.tolist()}")

    order = np.argsort(raw_extents)[::-1]
    length_axis = int(order[0])
    height_axis = int(order[1])
    width_axis = int(order[2])

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
    target_height_m = draft_m + air_draft_m if air_draft_m > 0 else None

    aligned[:, 0] *= loa_m / raw_extents[length_axis]
    aligned[:, 1] *= beam_m / raw_extents[width_axis]
    if target_height_m is not None:
        aligned[:, 2] *= target_height_m / raw_extents[height_axis]
    else:
        aligned[:, 2] *= loa_m / raw_extents[length_axis]

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
    if not GLB_MODEL_PATH.exists():
        raise FileNotFoundError(f"Original 3D model not found: {GLB_MODEL_PATH}")
    mesh = load_ship_glb(str(GLB_MODEL_PATH))
    vertices, faces, raw_extents = ship_mesh_to_plotly(mesh, ship, offset)
    fig.add_trace(go.Mesh3d(
        x=vertices[:, 0], y=vertices[:, 1], z=vertices[:, 2],
        i=faces[:, 0], j=faces[:, 1], k=faces[:, 2],
        color="gainsboro", flatshading=False, opacity=0.96,
        name=ship.get("Name", "Carnival Panorama"), hoverinfo="skip"
    ))

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
    model_dims = (
        float(np.ptp(vertices[:, 0])),
        float(np.ptp(vertices[:, 1])),
        float(np.ptp(vertices[:, 2])),
    )
    return model_dims

def _add_platform_origins(fig: go.Figure, profile_name: str, ship_offset: float) -> None:
    profile = get_berth_profile(profile_name)
    for station in ("FWD", "AFT"):
        p = profile.get("platforms", {}).get(station)
        if not p:
            continue
        x = float(p["x_m"]) + float(ship_offset)
        y = float(p["y_m"])
        z = float(p["z_m"])
        deck = "Deck 3" if station == "FWD" else "Deck 1"
        note = "27 m aft of extreme bow" if station == "FWD" else "14 m forward of extreme stern"
        fig.add_trace(go.Scatter3d(
            x=[x], y=[y], z=[z],
            mode="markers+text", text=[f"{station} MOORING PLATFORM — {deck}"],
            textposition="top center", marker=dict(size=8, symbol="cross"),
            name=f"{station} mooring platform", showlegend=False,
            hovertemplate=(f"{station} mooring platform — {deck}<br>{note}<br>"
                           "X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>")
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

def _add_berth_block(fig: go.Figure, bollards: pd.DataFrame, profile_name: str) -> None:
    """Draw a true 3D rectangular berth solid, not a 2D surface."""
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
        hovertemplate="Berth 3D solid<br>Top reference=%{z:.2f} m<br>Depth=%{customdata:.1f} m<extra></extra>",
        customdata=[BERTH_BLOCK_DEPTH_M] * 8,
    ))

def _add_berth_reference_lines(fig: go.Figure, bollards: pd.DataFrame) -> None:
    for station in ("FWD", "AFT"):
        part = bollards[bollards["measurement_station"].astype(str).str.upper() == station].sort_values("x_m")
        if len(part) >= 2:
            fig.add_trace(go.Scatter3d(
                x=part["x_m"].tolist(), y=part["y_m"].tolist(), z=part["z_m"].tolist(),
                mode="lines", line=dict(width=3, dash="dash"),
                name=f"Berth reference {station}", showlegend=False, hoverinfo="skip"
            ))

def _calibration_from_session(station: str) -> PlanCalibration:
    default = get_default_calibration(station)
    values = st.session_state.get(f"plan_cal_{station}")
    if not values:
        return default
    return PlanCalibration(
        station=station,
        anchor_u_px=float(values["u"]), anchor_v_px=float(values["v"]),
        anchor_x_m=default.anchor_x_m, anchor_y_m=default.anchor_y_m, anchor_z_m=default.anchor_z_m,
        scale_x_m_per_px=float(values["sx"]), scale_y_m_per_px=float(values["sy"]),
        rotation_deg=float(values["rot"]),
    )

def _render_reference_calibration_controls() -> tuple[bool, float, dict[str, PlanCalibration]]:
    with st.expander("🧭 Modalità B — Pianetti 2D sovrapposti al modello 3D", expanded=True):
        enabled = st.checkbox(
            "Mostra i pianetti 2D direttamente nella scena 3D",
            value=True,
            help="Reference layer בלבד: non modifica ancora le coordinate del solver.",
        )
        opacity = st.slider("Opacità pianetti", 0.05, 0.70, 0.24, 0.01)
        st.caption(
            "La sovrapposizione usa la mooring platform come punto di ancoraggio. "
            "+X = PRUA, +Y = PORT. Le coordinate ricavate dai pixel restano REFERENCE "
            "finché non vengono validate."
        )
        cols = st.columns(2)
        for col, station in zip(cols, ("FWD", "AFT")):
            default = get_default_calibration(station)
            key = f"plan_cal_{station}"
            if key not in st.session_state:
                st.session_state[key] = {
                    "u": default.anchor_u_px, "v": default.anchor_v_px,
                    "sx": default.scale_x_m_per_px, "sy": default.scale_y_m_per_px,
                    "rot": default.rotation_deg,
                }
            with col:
                st.markdown(f"**{station} — Deck {'3' if station == 'FWD' else '1'}**")
                st.number_input("Anchor U (pixel)", value=float(st.session_state[key]["u"]), step=1.0, key=f"{station}_u")
                st.number_input("Anchor V (pixel)", value=float(st.session_state[key]["v"]), step=1.0, key=f"{station}_v")
                st.number_input("Scala X (m/pixel)", value=float(st.session_state[key]["sx"]), step=0.001, format="%.5f", key=f"{station}_sx")
                st.number_input("Scala Y (m/pixel)", value=float(st.session_state[key]["sy"]), step=0.001, format="%.5f", key=f"{station}_sy")
                st.number_input("Rotazione (deg)", value=float(st.session_state[key]["rot"]), step=0.1, format="%.2f", key=f"{station}_rot")
                st.session_state[key] = {
                    "u": st.session_state[f"{station}_u"], "v": st.session_state[f"{station}_v"],
                    "sx": st.session_state[f"{station}_sx"], "sy": st.session_state[f"{station}_sy"],
                    "rot": st.session_state[f"{station}_rot"],
                }
        st.info(
            "I valori iniziali sono una calibrazione VISIVA PRELIMINARE basata sui riferimenti noti "
            "(27 m FWD, 14 m AFT e beam 37.20 m). Non vengono promossi automaticamente a geometria di calcolo."
        )
    return enabled, opacity, {s: _calibration_from_session(s) for s in ("FWD", "AFT")}

def _add_plan_overlay(fig: go.Figure, station: str, calibration: PlanCalibration, opacity: float, ship_offset: float) -> None:
    image = get_mooring_plan_image(station)
    # Keep enough detail for linework while avoiding an oversized Plotly surface.
    max_dim = 110
    scale = min(1.0, max_dim / max(image.size))
    small = image.resize((max(2, int(image.width * scale)), max(2, int(image.height * scale))))
    arr = np.asarray(small, dtype=float) / 255.0
    h, w = arr.shape
    sx_px = w / image.width
    sy_px = h / image.height
    u = np.arange(w) / sx_px
    v = np.arange(h) / sy_px
    U, V = np.meshgrid(u, v)

    # Apply calibration in the original image pixel coordinate system.
    x_local = (calibration.anchor_v_px - V) * calibration.scale_x_m_per_px
    y_local = -(U - calibration.anchor_u_px) * calibration.scale_y_m_per_px
    a = np.deg2rad(calibration.rotation_deg)
    X = calibration.anchor_x_m + ship_offset + x_local * np.cos(a) - y_local * np.sin(a)
    Y = calibration.anchor_y_m + x_local * np.sin(a) + y_local * np.cos(a)
    Z = np.full_like(X, calibration.anchor_z_m + 0.08)

    fig.add_trace(go.Surface(
        x=X, y=Y, z=Z, surfacecolor=arr,
        colorscale=[[0.0, "black"], [1.0, "white"]],
        cmin=0.0, cmax=1.0, showscale=False, opacity=opacity,
        name=f"{station} mooring plan — reference overlay",
        hoverinfo="skip", showlegend=True,
    ))

def _figure_3d(ship: dict, bollards: pd.DataFrame, offset: float, show_plans: bool, plan_opacity: float, calibrations: dict[str, PlanCalibration]) -> tuple[go.Figure, tuple[float, float, float]]:
    fig = go.Figure()
    model_dims = _add_ship(fig, ship, offset)
    _add_platform_origins(fig, "Ensenada Pier #2", offset)
    _add_berth_block(fig, bollards, "Ensenada Pier #2")
    _add_fixed_berth(fig, bollards)
    _add_berth_reference_lines(fig, bollards)
    if show_plans:
        for station in ("FWD", "AFT"):
            _add_plan_overlay(fig, station, calibrations[station], plan_opacity, offset)
    fig.update_layout(
        height=800,
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
            "FWD: origine rilievo su Deck 3, 27 m a poppavia dell'estrema prua. "
            "AFT: origine rilievo su Deck 1, 14 m a pruavia dell'estrema poppa. "
            "Le bitte sono fisse; la nave e le mooring platforms traslano soltanto longitudinalmente."
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
        show_plans, plan_opacity, calibrations = _render_reference_calibration_controls()
        st.subheader("🚢 Carnival Panorama — modello 3D + mooring platforms + banchina 3D + 12 bitte")
        try:
            fig, model_dims = _figure_3d(ship_dict, df, float(new_offset), show_plans, plan_opacity, calibrations)
            st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False, "scrollZoom": True})
            d1, d2, d3 = st.columns(3)
            d1.metric("Modello LOA", f"{model_dims[0]:.1f} m")
            d2.metric("Modello Beam", f"{model_dims[1]:.1f} m")
            d3.metric("Keel → Mast", f"{model_dims[2]:.1f} m")
            st.caption(
                "Modello calibrato sul profilo Carnival Panorama: LOA 323.44 m, Beam 37.20 m, Draft 8.5 m. "
                "I pianetti FWD/AFT sono reference overlay calibrati rispetto alle mooring platforms; "
                "non sono ancora sorgente automatica di coordinate del solver."
            )
        except Exception as exc:
            st.error(f"⚠️ Impossibile caricare il modello 3D originale: {exc}")
            st.info(f"Percorso previsto del GLB: {GLB_MODEL_PATH}")

        with st.expander("📄 Pianetti 2D originali — confronto di riferimento", expanded=False):
            a, b = st.columns(2)
            with a:
                st.image(get_mooring_plan_image("FWD"), caption="FWD Mooring Station — Deck 3", use_container_width=True)
            with b:
                st.image(get_mooring_plan_image("AFT"), caption="AFT Mooring Station — Deck 1", use_container_width=True)
        with st.expander("📐 Dati completi del rilievo", expanded=False):
            cols = ["bollard_id", "measurement_station", "side", "x_m", "y_m", "z_m", "survey_water_level_m"]
            st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.caption("Per questo porto occorre inserire un rilievo reale di banchina prima di visualizzare bitte e collegamenti nel modello 3D.")
