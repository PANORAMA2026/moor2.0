"""
views/tab_berth.py
Gestione layout banchina e modellazione 3D della nave.
Applica l'orientamento e lo scaling corretto degli assi CAD tridimensionali basandosi su DEFAULT_SHIP.
Posiziona la chiglia a -Draft (-8.5m) e la banchina a filo murata.
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

from config.constants import DEFAULT_SHIP, OFFSET_PLATFORM_FWD_M, OFFSET_PLATFORM_AFT_M
from database.db_manager import save_port_bollards_to_db, load_port_bollards_from_db
from utils.telemetry import calculate_bollard_coords

# Quota Z stimata delle stazioni telemetriche/d'ormeggio dal livello del mare (Z=0)
DEFAULT_OBS_HEIGHT_FWD = 12.0  # m
DEFAULT_OBS_HEIGHT_AFT = 7.5   # m


def calculate_bollard_coordinates(
    position_type: str,
    dist_inc: float,
    slope_deg: float,
    azimuth_deg: float,
    ship_dict: dict,
    berth_side: str = "Port Side",
):
    """
    Calcola le coordinate 3D reali delle bitte in banchina rispecchiando la murata d'ormeggio.
    """
    loa = ship_dict.get("LOA", DEFAULT_SHIP["LOA"])
    beam = ship_dict.get("Beam", DEFAULT_SHIP["Beam"])

    z_obs = (
        ship_dict.get("Obs_Platform_Fwd_Height", DEFAULT_OBS_HEIGHT_FWD)
        if position_type == "Prua"
        else ship_dict.get("Obs_Platform_Aft_Height", DEFAULT_OBS_HEIGHT_AFT)
    )

    platform_offset = (
        OFFSET_PLATFORM_FWD_M if position_type == "Prua" else OFFSET_PLATFORM_AFT_M
    )
    platform_type = "bow" if position_type == "Prua" else "stern"

    x_calc, y_calc, z_rel = calculate_bollard_coords(
        distance_inc=dist_inc,
        pitch_angle_deg=slope_deg,
        azimuth_deg=azimuth_deg,
        platform_type=platform_type,
        loa=loa,
        platform_offset=platform_offset,
    )

    # Offset Y banchina: Murata di dritta (-Beam/2) o sinistra (+Beam/2)
    side_sign = 1.0 if berth_side == "Port Side" else -1.0
    y_final = (beam / 2.0 + abs(y_calc)) * side_sign

    # Quota Z banchina/bitta rispetto al mare (Z = Z_obs - delta_Z)
    z_final = z_obs - abs(z_rel)
    dist_horiz = dist_inc * np.cos(np.radians(slope_deg))

    return round(dist_horiz, 2), x_calc, y_final, z_final


def generate_detailed_3d_ship(ship_dict: dict, offset_fugro: float = 0.0):
    """
    Carica la mesh CAD GLB, permuta gli assi grezzi per allinearli al sistema X=LOA, Y=Beam, Z=Height,
    e applica lo scaling tridimensionale guidato dalle specifiche della nave.
    """
    loa = ship_dict.get("LOA", DEFAULT_SHIP["LOA"])
    beam = ship_dict.get("Beam", DEFAULT_SHIP["Beam"])
    draft = ship_dict.get("Draft", DEFAULT_SHIP["Draft"])
    beam_max = ship_dict.get("Beam_Max", DEFAULT_SHIP["Beam_Max"])
    bridge_bow = ship_dict.get("Bridge_To_Bow", DEFAULT_SHIP["Bridge_To_Bow"])
    bridge_eye_h = ship_dict.get("Bridge_Eye_Height", DEFAULT_SHIP["Bridge_Eye_Height"])

    base_dir = Path(__file__).resolve().parent.parent
    mesh_path = base_dir / "asset" / "carnivalpanorama.glb"

    traces = []

    if mesh_path.exists():
        try:
            loaded = trimesh.load(str(mesh_path), force="mesh")
            mesh = (
                loaded.dump(concatenate=True)
                if isinstance(loaded, trimesh.Scene)
                else loaded
            )

            # 1. Identifica gli assi originali del file CAD in base alla dimensione dell'ingombro
            extents_orig = mesh.extents
            sorted_indices = np.argsort(extents_orig)[::-1]
            idx_x = sorted_indices[0]  # Dimensione maggiore -> LOA
            idx_y = sorted_indices[2]  # Dimensione minore -> Beam
            idx_z = sorted_indices[1]  # Dimensione intermedia -> Altezza

            # 2. Permuta i vertici per mapparli su [X=LOA, Y=Beam, Z=Altezza]
            verts_raw = mesh.vertices.copy()
            aligned_verts = np.zeros_like(verts_raw)
            aligned_verts[:, 0] = -verts_raw[:, idx_x]  # Inverte X per puntare la prua verso +X
            aligned_verts[:, 1] = verts_raw[:, idx_y]
            aligned_verts[:, 2] = verts_raw[:, idx_z]

            # 3. Calcola i fattori di scala reali basati sui parametri nave
            curr_loa = np.ptp(aligned_verts[:, 0])
            curr_beam = np.ptp(aligned_verts[:, 1])

            scale_x = loa / curr_loa if curr_loa != 0 else 1.0
            scale_y = beam / curr_beam if curr_beam != 0 else 1.0
            scale_z = (scale_x + scale_y) / 2.0  # Mantiene proporzionata l'altezza della sovrastruttura

            aligned_verts[:, 0] *= scale_x
            aligned_verts[:, 1] *= scale_y
            aligned_verts[:, 2] *= scale_z

            # 4. Centratura X=0, Y=0 e posizionamento della chiglia a Z = -Draft (-8.5m)
            min_x, max_x = np.min(aligned_verts[:, 0]), np.max(aligned_verts[:, 0])
            min_y, max_y = np.min(aligned_verts[:, 1]), np.max(aligned_verts[:, 1])
            min_z = np.min(aligned_verts[:, 2])

            aligned_verts[:, 0] = (aligned_verts[:, 0] - (min_x + max_x) / 2.0) + offset_fugro
            aligned_verts[:, 1] = aligned_verts[:, 1] - (min_y + max_y) / 2.0
            aligned_verts[:, 2] = (aligned_verts[:, 2] - min_z) - draft

            traces.append(
                go.Mesh3d(
                    x=aligned_verts[:, 0],
                    y=aligned_verts[:, 1],
                    z=aligned_verts[:, 2],
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
            st.error(f"⚠️ Errore durante il processing del modello CAD 3D: {e}")
    else:
        st.error(f"⚠️ File 3D non trovato nel percorso: {mesh_path}")

    # Visualizzazione Alette di Plancia
    bridge_x = (loa / 2.0 - bridge_bow) + offset_fugro
    wing_y = beam_max / 2.0
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

    # Assicura la presenza dei parametri nave predefiniti
    for key, val in DEFAULT_SHIP.items():
        ship_dict.setdefault(key, val)

    ship_dict.setdefault("Obs_Platform_Fwd_Height", DEFAULT_OBS_HEIGHT_FWD)
    ship_dict.setdefault("Obs_Platform_Aft_Height", DEFAULT_OBS_HEIGHT_AFT)

    offset_fugro = float(st.session_state.get("offset_fugro_m", 0.0))

    col_info, col_side = st.columns([2, 1])
    with col_info:
        st.caption(
            f"🚢 **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** | "
            f"Beam: **{ship_dict.get('Beam')}m** | Draft: **{ship_dict.get('Draft')}m** | "
            f"Offset FUGRO: **{offset_fugro:+.2f} m**"
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
        st.info("📐 **Rilevamento Telemetria:** Inserisci le misurazioni per ciascuna bitta.")

        st.subheader(f"⚓ Stazione Prua (Quota Obs: {ship_dict['Obs_Platform_Fwd_Height']}m)")
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
                "bollard_id": st.column_config.TextColumn("ID Bitta", required=True),
                "Dist_Inclinata_m": st.column_config.NumberColumn("Dist. Telemetro (m)", default=0.0, step=0.5),
                "Pendenza_deg": st.column_config.NumberColumn("Pendenza (°)", default=0.0, step=1.0),
                "Azimut_deg": st.column_config.NumberColumn("Azimut (°)", default=0.0, step=1.0),
                "SWL_Bitta_t": st.column_config.NumberColumn("SWL (t)", default=100.0, min_value=10.0),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["In Uso", "Disponibile", "Danneggiata"], default="Disponibile"),
            },
        )

        st.divider()

        st.subheader(f"⚓ Stazione Poppa (Quota Obs: {ship_dict['Obs_Platform_Aft_Height']}m)")
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
                "bollard_id": st.column_config.TextColumn("ID Bitta", required=True),
                "Dist_Inclinata_m": st.column_config.NumberColumn("Dist. Telemetro (m)", default=0.0, step=0.5),
                "Pendenza_deg": st.column_config.NumberColumn("Pendenza (°)", default=0.0, step=1.0),
                "Azimut_deg": st.column_config.NumberColumn("Azimut (°)", default=0.0, step=1.0),
                "SWL_Bitta_t": st.column_config.NumberColumn("SWL (t)", default=100.0, min_value=10.0),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["In Uso", "Disponibile", "Danneggiata"], default="Disponibile"),
            },
        )

        if st.button("💾 Salva Layout Permanentemente su DB", type="primary"):
            updated_rows = []

            for idx, row in edited_prua.iterrows():
                b_id = str(row.get("bollard_id", f"BP{idx+1}")).strip() or f"BP{idx+1}"
                d_inc = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                az_deg = float(row.get("Azimut_deg", 0.0) or 0.0)

                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    "Prua", d_inc, p_deg, az_deg, ship_dict, berth_side=berth_side
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
                    "SWL_Bitta_t": float(row.get("SWL_Bitta_t", 100.0) or 100.0),
                    "Stato": row.get("Stato", "Disponibile"),
                    "is_frozen": True,
                })

            for idx, row in edited_poppa.iterrows():
                b_id = str(row.get("bollard_id", f"BA{idx+1}")).strip() or f"BA{idx+1}"
                d_inc = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                az_deg = float(row.get("Azimut_deg", 0.0) or 0.0)

                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    "Poppa", d_inc, p_deg, az_deg, ship_dict, berth_side=berth_side
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
                    "SWL_Bitta_t": float(row.get("SWL_Bitta_t", 100.0) or 100.0),
                    "Stato": row.get("Stato", "Disponibile"),
                    "is_frozen": True,
                })

            final_df = pd.DataFrame(updated_rows)
            st.session_state.ports_bollards[selected_port] = final_df
            save_port_bollards_to_db(selected_port, final_df)
            st.success(f"Layout salvato nel database per {selected_port} ({berth_side})!")
            st.rerun()

    with col_map:
        st.subheader("🧊 Modellazione 3D Volumetric")
        fig = go.Figure()

        for trace in generate_detailed_3d_ship(ship_dict, offset_fugro=offset_fugro):
            fig.add_trace(trace)

        loa = ship_dict.get("LOA", DEFAULT_SHIP["LOA"])
        beam = ship_dict.get("Beam", DEFAULT_SHIP["Beam"])

        # Costruzione solido banchina posizionato esatto a filo murata (Y = ±Beam/2)
        side_multiplier = 1.0 if berth_side == "Port Side" else -1.0
        berth_y_start = (beam / 2.0) * side_multiplier
        berth_y_end = berth_y_start + (12.0 * side_multiplier)

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
                z=[-12, -12, -12, -12, 0, 0, 0, 0],
                i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0],
                j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                color="slategrey",
                opacity=0.6,
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
                    textposition="top center",
                    marker=dict(size=7, color="red", symbol="square"),
                )
            )

        if calculate_line_geometry is not None and "lines_inventory" in st.session_state:
            try:
                lines_inv = st.session_state.lines_inventory
                geom_df = calculate_line_geometry(
                    lines_inv, df_bollards, loa=loa, offset_fugro=offset_fugro
                )

                if geom_df is not None and not geom_df.empty:
                    if solve_line_tensions_3d is not None:
                        sim_df = solve_line_tensions_3d(
                            geom_df,
                            {"Fx_total_t": 0.0, "Fy_total_t": 0.0, "Mz_total_tm": 0.0},
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
