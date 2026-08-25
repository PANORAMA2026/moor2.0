"""
views/tab_berth.py
Modulo per la gestione del layout di banchina:
- Banchina in 3D posizionata a Z=0
- Nave 2D sopraelevata alla quota calcolata in base alla pendenza dei cavi
- Observation Platforms posizionate sul piano nave sopraelevato
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """Calcola le coordinate X, Y, Z della bitta rispetto alla piattaforma."""
    slope_rad = np.radians(slope_deg)

    # Distanza orizzontale e dislivello Z (inclinazione cavo)
    dist_horiz = dist_inc * np.cos(slope_rad)
    z_m = -1.0 * (dist_inc * np.sin(slope_rad))

    if position_type == "Prua":
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_m = x_platform - dist_horiz
    else:
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_m = x_platform + dist_horiz

    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def build_3d_dock_mesh(x_min, x_max, y_front, width_y=15.0, depth_z=4.0):
    """Crea la struttura 3D della banchina con estradosso a quota Z=0."""
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
    st.header(f"🗺️ Layout Banchina 3D & Nave Sopraelevata — {selected_port}")
    st.caption(
        "📐 **Telemetro Laser:** Modifica **Distanza** e **Pendenza**. "
        "La nave 2D si posiziona automaticamente sopraelevata rispetto alla banchina in base al dislivello calcolato."
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcolo coordinate bitte e media della pendenza/quota nave
    z_offsets = []
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

        # Dislivello verticale piattaforma -> bitta
        z_offsets.append(abs(z_calc))

    # Quota della nave (se dislivello 0, usa un'altezza predefinita di 8m)
    ship_z_elevation = max(z_offsets) if any(z_offsets) else 8.0

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

    # --- SCENA 3D ---
    with col_map:
        st.subheader("🧊 Vista 3D: Nave Sopraelevata & Banchina")

        loa = ship_dict["LOA"]
        beam = ship_dict["Beam"]

        fig = go.Figure()

        # 1. Banchina 3D a quota Z=0
        berth_front_y = (beam / 2.0) + 6.4
        bx, by, bz, bi, bj, bk = build_3d_dock_mesh(
            x_min=-loa * 0.7,
            x_max=loa * 0.7,
            y_front=berth_front_y,
            width_y=12.0,
            depth_z=5.0,
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
                name="Struttura Banchina (Z=0)",
            )
        )

        # 2. Nave 2D sopraelevata a quota Z = ship_z_elevation
        ship_x_mesh = [-loa / 2, loa / 2, loa / 2, -loa / 2]
        ship_y_mesh = [-beam / 2, -beam / 2, beam / 2, beam / 2]
        ship_z_mesh = [
            ship_z_elevation,
            ship_z_elevation,
            ship_z_elevation,
            ship_z_elevation,
        ]

        fig.add_trace(
            go.Mesh3d(
                x=ship_x_mesh,
                y=ship_y_mesh,
                z=ship_z_mesh,
                i=[0, 0],
                j=[1, 2],
                k=[2, 3],
                color="navy",
                opacity=0.45,
                name=f"Piano Nave (+{ship_z_elevation:.1f}m)",
            )
        )

        # Contorno 2D perimetro nave alla quota sopraelevata
        ship_x_line = [-loa / 2, loa / 2, loa / 2, -loa / 2, -loa / 2]
        ship_y_line = [-beam / 2, -beam / 2, beam / 2, beam / 2, -beam / 2]
        ship_z_line = [ship_z_elevation] * 5

        fig.add_trace(
            go.Scatter3d(
                x=ship_x_line,
                y=ship_y_line,
                z=ship_z_line,
                mode="lines",
                name="Perimetro Nave",
                line=dict(color="blue", width=4),
            )
        )

        # 3. Observation Platforms sulla nave alla quota Z sopraelevata
        plat_fwd_x = (loa / 2.0) - OFFSET_PLATFORM_FWD_M
        plat_aft_x = (-loa / 2.0) + OFFSET_PLATFORM_AFT_M

        fig.add_trace(
            go.Scatter3d(
                x=[plat_fwd_x, plat_aft_x],
                y=[0, 0],
                z=[ship_z_elevation, ship_z_elevation],
                mode="markers+text",
                name="Observation Platforms",
                text=["Obs Fwd", "Obs Aft"],
                textposition="top center",
                marker=dict(size=8, color="gold", symbol="diamond"),
            )
        )

        # 4. Bitte sulla banchina (Quota Z=0 / relative a banchina)
        fig.add_trace(
            go.Scatter3d(
                x=df_bollards["X_Coordinata_m"],
                y=df_bollards["Y_Coordinata_m"],
                z=[0.0]
                * len(
                    df_bollards
                ),  # Posizionate sul piano banchina a quota 0
                mode="markers+text",
                name="Bitte Banchina (Z=0)",
                text=df_bollards["bollard_id"],
                textposition="bottom center",
                marker=dict(size=7, color="red", symbol="square"),
            )
        )

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
