"""
views/tab_berth.py
Modulo per la gestione del layout di banchina con:
- Nave in 2D (Sagoma piana sul piano di galleggiamento Z=0)
- Banchina in 3D (Solido banchina + bitte tridimensionali)
- Calcolo automatico X, Y, Z dalle Observation Platform (Prua/Poppa)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """Calcola le coordinate X, Y, Z della bitta partendo da Distanza Inclinata e Pendenza

    misurate dalle Observation Platform di Prua / Poppa.
    """
    slope_rad = np.radians(slope_deg)

    # 1. Distanza orizzontale e delta Z
    dist_horiz = dist_inc * np.cos(slope_rad)
    z_m = -1.0 * (dist_inc * np.sin(slope_rad))

    # 2. Coordinata X basata sull'offset delle piattaforme
    if position_type == "Prua":
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_m = x_platform - dist_horiz
    else:
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_m = x_platform + dist_horiz

    # 3. Coordinata Y (filo banchina dal centro nave)
    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def build_3d_dock_mesh(x_min, x_max, y_front, width_y=15.0, depth_z=5.0):
    """Crea una struttura volumetrica 3D (Mesh3d) della banchina banchinata."""
    y_back = y_front + width_y
    z_top = 0.0
    z_bottom = -depth_z

    x = [
        x_min,
        x_max,
        x_max,
        x_min,
        x_min,
        x_max,
        x_max,
        x_min,
    ]
    y = [
        y_front,
        y_front,
        y_back,
        y_back,
        y_front,
        y_front,
        y_back,
        y_back,
    ]
    z = [
        z_bottom,
        z_bottom,
        z_bottom,
        z_bottom,
        z_top,
        z_top,
        z_top,
        z_top,
    ]

    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]

    return x, y, z, i, j, k


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina 3D & Nave 2D — {selected_port}")
    st.caption(
        "📐 Inserisci **Distanza** e **Pendenza** dal telemetro. "
        "La nave viene proiettata in 2D sul galleggiamento ($Z=0$), mentre la banchina e le bitte sono modellate in 3D."
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcolo automatico di X, Y, Z per ogni bitta
    for idx, row in df_bollards.iterrows():
        pos = row.get("Posizione", "Prua")
        d_inc = float(row.get("Dist_Inclinata_m", 15.0))
        p_deg = float(row.get("Pendenza_deg", 0.0))

        d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
            pos, d_inc, p_deg, ship_dict["LOA"], ship_dict["Beam"]
        )

        df_bollards.at[idx, "Dist_Orizzontale_m"] = d_horiz
        df_bollards.at[idx, "X_Coordinata_m"] = x_calc
        df_bollards.at[idx, "Y_Coordinata_m"] = y_calc
        df_bollards.at[idx, "Z_Altezza_m"] = z_calc
        df_bollards.at[idx, "bollard_x_m"] = x_calc
        df_bollards.at[idx, "bollard_y_m"] = y_calc
        df_bollards.at[idx, "bollard_z_m"] = z_calc

    col_edit, col_map = st.columns([1, 1.2])

    # --- TABELLA INPUT ---
    with col_edit:
        st.subheader("📋 Input Telemetro Laser")

        edited_df = st.data_editor(
            df_bollards[[
                "bollard_id",
                "Posizione",
                "Dist_Inclinata_m",
                "Pendenza_deg",
                "SWL_Bitta_t",
                "Stato",
            ]],
            column_config={
                "bollard_id": st.column_config.TextColumn(
                    "ID Bitta", disabled=True
                ),
                "Posizione": st.column_config.SelectboxColumn(
                    "Stazione / Piattaforma",
                    options=["Prua", "Poppa"],
                    required=True,
                ),
                "Dist_Inclinata_m": st.column_config.NumberColumn(
                    "Distanza (m)",
                    min_value=0.0,
                    max_value=300.0,
                    step=0.5,
                    format="%.1f m",
                ),
                "Pendenza_deg": st.column_config.NumberColumn(
                    "Pendenza (°)",
                    min_value=-45.0,
                    max_value=45.0,
                    step=0.5,
                    format="%.1f°",
                ),
                "SWL_Bitta_t": st.column_config.NumberColumn(
                    "SWL (ton)", min_value=10, max_value=300, step=5
                ),
                "Stato": st.column_config.SelectboxColumn(
                    "Stato", options=["Attivo", "Inattivo"]
                ),
            },
            hide_index=True,
            use_container_width=True,
        )

        if st.button("💾 Aggiorna Layout & Salva Coordinate"):
            for idx, row in edited_df.iterrows():
                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    row["Posizione"],
                    row["Dist_Inclinata_m"],
                    row["Pendenza_deg"],
                    ship_dict["LOA"],
                    ship_dict["Beam"],
                )
                edited_df.at[idx, "Dist_Orizzontale_m"] = d_horiz
                edited_df.at[idx, "X_Coordinata_m"] = x_calc
                edited_df.at[idx, "Y_Coordinata_m"] = y_calc
                edited_df.at[idx, "Z_Altezza_m"] = z_calc
                edited_df.at[idx, "bollard_x_m"] = x_calc
                edited_df.at[idx, "bollard_y_m"] = y_calc
                edited_df.at[idx, "bollard_z_m"] = z_calc

            st.session_state.ports_bollards[selected_port] = edited_df
            st.success("Layout aggiornato con successo!")
            st.rerun()

    # --- SCENA 3D (Banchina 3D + Nave 2D) ---
    with col_map:
        st.subheader("🧊 Vista 3D: Banchina Tridimensionale & Nave 2D")

        loa = ship_dict["LOA"]
        beam = ship_dict["Beam"]
        freeboard = ship_dict.get("Freeboard", 12.0)

        fig = go.Figure()

        # 1. Banchina 3D (Mesh Tridimensionale)
        berth_front_y = (beam / 2.0) + 6.4
        bx, by, bz, bi, bj, bk = build_3d_dock_mesh(
            x_min=-loa * 0.7,
            x_max=loa * 0.7,
            y_front=berth_front_y,
            width_y=12.0,
            depth_z=6.0,
        )
        fig.add_trace(
            go.Mesh3d(
                x=bx,
                y=by,
                z=bz,
                i=bi,
                j=bj,
                k=bk,
                color="slategrey",
                opacity=0.6,
                name="Struttura Banchina 3D",
            )
        )

        # 2. Nave 2D (Sagoma sul piano Z=0)
        ship_x2d = [-loa / 2, loa / 2, loa / 2, -loa / 2, -loa / 2]
        ship_y2d = [-beam / 2, -beam / 2, beam / 2, beam / 2, -beam / 2]
        ship_z2d = [0, 0, 0, 0, 0]

        fig.add_trace(
            go.Scatter3d(
                x=ship_x2d,
                y=ship_y2d,
                z=ship_z2d,
                mode="lines",
                fill="toself",
                name="Sagoma Nave 2D (Piano Z=0)",
                line=dict(color="navy", width=5),
            )
        )

        # 3. Observation Platforms 2D (Riferimenti sulle stazioni di Prua e Poppa)
        plat_fwd_x = (loa / 2.0) - OFFSET_PLATFORM_FWD_M
        plat_aft_x = (-loa / 2.0) + OFFSET_PLATFORM_AFT_M

        fig.add_trace(
            go.Scatter3d(
                x=[plat_fwd_x, plat_aft_x],
                y=[0, 0],
                z=[freeboard, freeboard],
                mode="markers+text",
                name="Observation Platforms",
                text=["Obs Fwd", "Obs Aft"],
                textposition="top center",
                marker=dict(size=8, color="gold", symbol="diamond"),
            )
        )

        # 4. Bitte in 3D (Coordinate X, Y, Z Calcolate)
        fig.add_trace(
            go.Scatter3d(
                x=df_bollards["X_Coordinata_m"],
                y=df_bollards["Y_Coordinata_m"],
                z=df_bollards["Z_Altezza_m"],
                mode="markers+text",
                name="Bitte Banchina (3D)",
                text=df_bollards["bollard_id"],
                textposition="bottom center",
                marker=dict(size=7, color="red", symbol="square"),
            )
        )

        # Configurazione telecamera e assi
        fig.update_layout(
            scene=dict(
                xaxis_title="X (m - Longitudinale)",
                yaxis_title="Y (m - Trasversale)",
                zaxis_title="Z (m - Verticale)",
                aspectmode="data",
                camera=dict(eye=dict(x=-1.6, y=-1.6, z=1.3)),
            ),
            height=550,
            margin=dict(l=0, r=0, b=0, t=30),
            showlegend=True,
        )

        st.plotly_chart(fig, use_container_width=True)
