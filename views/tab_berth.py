"""
views/tab_berth.py
Gestione layout banchina separata in due stazioni (Prua e Poppa).
Calcolo coordinate 3D (con Azimut), calcolo rigidezza con pretensione e passaggio dati allo State.
Modello 3D da file CAD (.glb) con rotazione e scaling corretto, e selezione murata d'ormeggio.
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import trimesh

try:
    from core.line_mechanics import calculate_line_geometry, solve_line_tensions_3d
except ImportError:
    calculate_line_geometry = None
    solve_line_tensions_3d = None

from database.db_manager import save_port_bollards_to_db, load_port_bollards_from_db
from utils.telemetry import calculate_bollard_coords

OFFSET_PLATFORM_FWD_M = 25.0
OFFSET_PLATFORM_AFT_M = 14.0


def calculate_bollard_coordinates(
    position_type: str,
    dist_inc: float,
    slope_deg: float,
    azimuth_deg: float,
    ship_loa: float,
    ship_beam: float,
    berth_side: str = "Port Side",
):
    """Wrapper di supporto che richiama le funzioni di telemetria per uniformare i dati."""
    platform_offset = (
        OFFSET_PLATFORM_FWD_M if position_type == "Prua" else OFFSET_PLATFORM_AFT_M
    )
    platform_type = "bow" if position_type == "Prua" else "stern"

    x_calc, y_calc, z_calc = calculate_bollard_coords(
        distance_inc=dist_inc,
        pitch_angle_deg=slope_deg,
        azimuth_deg=azimuth_deg,
        platform_type=platform_type,
        loa=ship_loa,
        platform_offset=platform_offset,
    )

    # Adatta il segno di Y in base alla murata di ormeggio
    if berth_side == "Starboard Side":
        y_calc = -abs(y_calc)
    else:
        y_calc = abs(y_calc)

    dist_horiz = dist_inc * np.cos(np.radians(slope_deg))

    return round(dist_horiz, 2), x_calc, y_calc, z_calc


def generate_detailed_3d_ship(ship_dict, offset_fugro: float = 0.0):
    """
    Carica il modello CAD 3D .glb da asset/carnivalpanorama.glb,
    applica le rotazioni e scala le dimensioni mantenendo la geometria coerente.
    """
    loa = ship_dict.get("LOA", 323.44)
    beam = ship_dict.get("Beam", 37.20)
    bridge_bow = ship_dict.get("Bridge_To_Bow", 39.50)
    bridge_eye_h = ship_dict.get("Bridge_Eye_Height", 26.40)

    base_dir = Path(__file__).resolve().parent.parent
    mesh_path = base_dir / "asset" / "carnivalpanorama.glb"

    traces = []

    if mesh_path.exists():
        try:
            loaded = trimesh.load(str(mesh_path), force="mesh")
            if isinstance(loaded, trimesh.Scene):
                mesh = loaded.dump(concatenate=True)
            else:
                mesh = loaded

            # 1. Rotazione per orientare la nave: X = Lunghezza, Y = Larghezza, Z = Altezza
            Rz = trimesh.transformations.rotation_matrix(np.radians(90), [0, 0, 1])
            Rx = trimesh.transformations.rotation_matrix(np.radians(90), [1, 0, 0])
            
            mesh.apply_transform(Rz)
            mesh.apply_transform(Rx)

            # 2. Ricalcolo bounding box e dimensioni sulla mesh ruotata
            extents = mesh.extents
            bounds = mesh.bounds

            # 3. Scaling corretto e coerente per ciascun asse
            scale_x = loa / extents[0] if extents[0] != 0 else 1.0
            scale_y = beam / extents[1] if extents[1] != 0 else 1.0
            scale_z = scale_x  # Mantiene la proporzione verticale reale

            vertices = mesh.vertices.copy()
            vertices[:, 0] = vertices[:, 0] * scale_x
            vertices[:, 1] = vertices[:, 1] * scale_y
            vertices[:, 2] = vertices[:, 2] * scale_z

            # 4. Centratura longitudinale (Midship X=0) e offset Z (Chiglia a Z=0)
            x_center = ((bounds[0][0] + bounds[1][0]) / 2.0) * scale_x
            z_min = bounds[0][2] * scale_z

            vertices[:, 0] = (vertices[:, 0] - x_center) + offset_fugro
            vertices[:, 2] = vertices[:, 2] - z_min

            traces.append(
                go.Mesh3d(
                    x=vertices[:, 0],
                    y=vertices[:, 1],
                    z=vertices[:, 2],
                    i=mesh.faces[:, 0],
                    j=mesh.faces[:, 1],
                    k=mesh.faces[:, 2],
                    color="gainsboro",
                    flatshading=True,
                    opacity=0.95,
                    name=ship_dict.get("Name", "Carnival Panorama"),
                    hoverinfo="skip",
                )
            )
        except Exception as e:
            st.error(f"⚠️ Errore caricamento modello 3D GLB: {e}")
    else:
        st.error(f"⚠️ File 3D non trovato nel percorso: {mesh_path}")

    # Alette di Plancia
    bridge_x = (loa / 2.0 - bridge_bow) + offset_fugro
    wing_y = ship_dict.get("Beam_Max", 49.40) / 2.0
    traces.append(
        go.Scatter3d(
            x=[bridge_x, bridge_x],
            y=[-wing_y, wing_y],
            z=[bridge_eye_h, bridge_eye_h],
            mode="lines+markers",
            line=dict(color="red", width=8),
            marker=dict(size=5, color="darkred"),
            name="Alette di Plancia",
            hoverinfo="skip",
        )
    )

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina — {selected_port}")

    offset_fugro = float(st.session_state.get("offset_fugro_m", 0.0))

    # Selettore Murata di Ormeggio
    col_info, col_side = st.columns([2, 1])
    with col_info:
        st.caption(
            f"🚢 **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** |"
            f" Offset FUGRO: **{offset_fugro:+.2f} m**"
        )
    with col_side:
        berth_side = st.radio(
            "Murata di Ormeggio:",
            ["Port Side", "Starboard Side"],
            horizontal=True,
            key="berth_side_selection",
        )

    if "ports_bollards" not in st.session_state:
        st.session_state.ports_bollards = {}

    if selected_port not in st.session_state.ports_bollards:
        st.session_state.ports_bollards[selected_port] = (
            load_port_bollards_from_db(selected_port)
        )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    if "Azimut_deg" not in df_bollards.columns:
        df_bollards["Azimut_deg"] = 0.0

    col_edit, col_map = st.columns([1.1, 1.1])

    with col_edit:
        st.info(
            "📐 **Rilevamento Telemetria:** Inserisci Distanza Inclinata,"
            " Pendenza Verticale e Azimut per ogni bitta."
        )

        st.subheader("⚓ Stazione di Prua (Fwd Observation Platform)")
        df_prua = (
            df_bollards[df_bollards["Posizione"] == "Prua"].copy()
            if not df_bollards.empty
            else pd.DataFrame()
        )
        edited_prua = st.data_editor(
            df_prua[[
                "bollard_id",
                "Dist_Inclinata_m",
                "Pendenza_deg",
                "Azimut_deg",
                "SWL_Bitta_t",
                "Stato",
            ]],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="editor_prua",
            column_config={
                "bollard_id": st.column_config.TextColumn(
                    "ID Bitta", required=True
                ),
                "Dist_Inclinata_m": st.column_config.NumberColumn(
                    "Dist. Telemetro (m)", default=0.0, step=0.5
                ),
                "Pendenza_deg": st.column_config.NumberColumn(
                    "Pendenza (°)", default=0.0, step=1.0
                ),
                "Azimut_deg": st.column_config.NumberColumn(
                    "Azimut (°)", default=0.0, step=1.0
                ),
                "SWL_Bitta_t": st.column_config.NumberColumn(
                    "SWL (t)", default=100.0, min_value=10.0
                ),
                "Stato": st.column_config.SelectboxColumn(
                    "Stato",
                    options=["In Uso", "Disponibile", "Danneggiata"],
                    default="Disponibile",
                ),
            },
        )

        st.divider()

        st.subheader("⚓ Stazione di Poppa (Aft Observation Platform)")
        df_poppa = (
            df_bollards[df_bollards["Posizione"] == "Poppa"].copy()
            if not df_bollards.empty
            else pd.DataFrame()
        )
        edited_poppa = st.data_editor(
            df_poppa[[
                "bollard_id",
                "Dist_Inclinata_m",
                "Pendenza_deg",
                "Azimut_deg",
                "SWL_Bitta_t",
                "Stato",
            ]],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            key="editor_poppa",
            column_config={
                "bollard_id": st.column_config.TextColumn(
                    "ID Bitta", required=True
                ),
                "Dist_Inclinata_m": st.column_config.NumberColumn(
                    "Dist. Telemetro (m)", default=0.0, step=0.5
                ),
                "Pendenza_deg": st.column_config.NumberColumn(
                    "Pendenza (°)", default=0.0, step=1.0
                ),
                "Azimut_deg": st.column_config.NumberColumn(
                    "Azimut (°)", default=0.0, step=1.0
                ),
                "SWL_Bitta_t": st.column_config.NumberColumn(
                    "SWL (t)", default=100.0, min_value=10.0
                ),
                "Stato": st.column_config.SelectboxColumn(
                    "Stato",
                    options=["In Uso", "Disponibile", "Danneggiata"],
                    default="Disponibile",
                ),
            },
        )

        if st.button("💾 Salva Layout Permanentemente su DB", type="primary"):
            updated_rows = []

            for idx, row in edited_prua.iterrows():
                b_id = (
                    str(row.get("bollard_id", f"BP{idx+1}")).strip()
                    or f"BP{idx+1}"
                )
                d_inc = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                az_deg = float(row.get("Azimut_deg", 0.0) or 0.0)

                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    "Prua",
                    d_inc,
                    p_deg,
                    az_deg,
                    ship_dict["LOA"],
                    ship_dict["Beam"],
                    berth_side=berth_side,
                )
                updated_rows.append({
                    "bollard_id": b_id,
                    "Posizione": "Prua",
                    "Dist_Inclinata_m": d_inc,
                    "Pendenza_deg": p_deg,
                    "Azimut_deg": az_deg,
                    "Dist_Orizzontale_m": d_horiz,
                    "X_Coordinata_m": x_calc,
                    "Y_Coordinata_m": y_calc,
                    "Z_Altezza_m": z_calc,
                    "bollard_x_m": x_calc,
                    "bollard_y_m": y_calc,
                    "bollard_z_m": z_calc,
                    "SWL_Bitta_t": float(
                        row.get("SWL_Bitta_t", 100.0) or 100.0
                    ),
                    "Stato": row.get("Stato", "Disponibile"),
                    "is_frozen": True,
                })

            for idx, row in edited_poppa.iterrows():
                b_id = (
                    str(row.get("bollard_id", f"BA{idx+1}")).strip()
                    or f"BA{idx+1}"
                )
                d_inc = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                az_deg = float(row.get("Azimut_deg", 0.0) or 0.0)

                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    "Poppa",
                    d_inc,
                    p_deg,
                    az_deg,
                    ship_dict["LOA"],
                    ship_dict["Beam"],
                    berth_side=berth_side,
                )
                updated_rows.append({
                    "bollard_id": b_id,
                    "Posizione": "Poppa",
                    "Dist_Inclinata_m": d_inc,
                    "Pendenza_deg": p_deg,
                    "Azimut_deg": az_deg,
                    "Dist_Orizzontale_m": d_horiz,
                    "X_Coordinata_m": x_calc,
                    "Y_Coordinata_m": y_calc,
                    "Z_Altezza_m": z_calc,
                    "bollard_x_m": x_calc,
                    "bollard_y_m": y_calc,
                    "bollard_z_m": z_calc,
                    "SWL_Bitta_t": float(
                        row.get("SWL_Bitta_t", 100.0) or 100.0
                    ),
                    "Stato": row.get("Stato", "Disponibile"),
                    "is_frozen": True,
                })

            final_df = pd.DataFrame(updated_rows)
            st.session_state.ports_bollards[selected_port] = final_df

            save_port_bollards_to_db(selected_port, final_df)
            st.success(
                f"Layout salvato nel database per {selected_port} ({berth_side})!"
            )
            st.rerun()

    with col_map:
        st.subheader("🧊 Modellazione 3D Volumetric")
        fig = go.Figure()

        for trace in generate_detailed_3d_ship(
            ship_dict, offset_fugro=offset_fugro
        ):
            fig.add_trace(trace)

        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)

        # Posizionamento coerente della banchina in base al lato selezionato
        side_multiplier = 1.0 if berth_side == "Port Side" else -1.0
        berth_y_start = (beam / 2.0 + 6.4) * side_multiplier
        berth_y_end = berth_y_start + (15.0 * side_multiplier)

        fig.add_trace(
            go.Mesh3d(
                x=[
                    -loa * 0.65,
                    loa * 0.65,
                    loa * 0.65,
                    -loa * 0.65,
                    -loa * 0.65,
                    loa * 0.65,
                    loa * 0.65,
                    -loa * 0.65,
                ],
                y=[
                    berth_y_start,
                    berth_y_start,
                    berth_y_end,
                    berth_y_end,
                    berth_y_start,
                    berth_y_start,
                    berth_y_end,
                    berth_y_end,
                ],
                z=[-6, -6, -6, -6, 0, 0, 0, 0],
                i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0],
                j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                color="slategrey",
                opacity=0.5,
                name=f"Banchina ({berth_side})",
            )
        )

        if not df_bollards.empty and "X_Coordinata_m" in df_bollards.columns:
            fig.add_trace(
                go.Scatter3d(
                    x=df_bollards["X_Coordinata_m"],
                    y=df_bollards["Y_Coordinata_m"],
                    z=df_bollards["Z_Altezza_m"],
                    mode="markers+text",
                    name="Bitte Banchina",
                    text=df_bollards["bollard_id"],
                    textposition="bottom center",
                    marker=dict(size=7, color="red", symbol="square"),
                )
            )

        if (
            calculate_line_geometry is not None
            and "lines_inventory" in st.session_state
        ):
            try:
                lines_inv = st.session_state.lines_inventory
                geom_df = calculate_line_geometry(
                    lines_inv,
                    df_bollards,
                    loa=loa,
                    offset_fugro=offset_fugro,
                )

                if geom_df is not None and not geom_df.empty:
                    if solve_line_tensions_3d is not None:
                        sim_df = solve_line_tensions_3d(
                            geom_df,
                            {
                                "Fx_total_t": 0.0,
                                "Fy_total_t": 0.0,
                                "Mz_total_tm": 0.0,
                            },
                            pretension_pct=10.0,
                        )
                        st.session_state["latest_mooring_results"] = sim_df

                    for _, line in geom_df.iterrows():
                        fig.add_trace(
                            go.Scatter3d(
                                x=[line["chock_x_m"], line["bollard_x_m"]],
                                y=[line["chock_y_m"], line["bollard_y_m"]],
                                z=[line["chock_z_m"], line["bollard_z_m"]],
                                mode="lines",
                                line=dict(color="orange", width=4),
                                showlegend=False,
                            )
                        )
            except Exception as e:
                st.warning(f"Errore nel calcolo delle linee 3D: {e}")

        fig.update_layout(
            scene=dict(
                xaxis=dict(title="X (m)"),
                yaxis=dict(title="Y (m)"),
                zaxis=dict(title="Z (m)"),
                aspectmode="data",
            ),
            height=650,
            margin=dict(l=0, r=0, b=0, t=30),
        )
        st.plotly_chart(fig, use_container_width=True)
