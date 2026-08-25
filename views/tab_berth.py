"""
views/tab_berth.py
Modulo per la gestione del layout di banchina con vista 3D della nave,
observation platforms e posizionamento bitte basato su telemetro (Distanza e Pendenza).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import degli offset delle piattaforme di osservazione
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
        # Platform Prua = LOA/2 - OFFSET_PLATFORM_FWD_M (es. 21m)
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_m = x_platform - dist_horiz
    else:
        # Platform Poppa = -LOA/2 + OFFSET_PLATFORM_AFT_M (es. 14m)
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_m = x_platform + dist_horiz

    # 3. Coordinata Y (distanza filo banchina dal centro nave)
    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def build_3d_ship_mesh(loa, beam, draft, freeboard):
    """Crea una struttura stilizzata 3D (Mesh3d) dello scafo della nave."""
    half_l = loa / 2.0
    half_b = beam / 2.0
    z_bottom = -draft
    z_deck = freeboard

    # Vertici del parallelepipedo scafo stilizzato
    x = [
        -half_l,
        half_l,
        half_l,
        -half_l,
        -half_l,
        half_l,
        half_l,
        -half_l,
    ]
    y = [
        -half_b,
        -half_b,
        half_b,
        half_b,
        -half_b,
        -half_b,
        half_b,
        half_b,
    ]
    z = [
        z_bottom,
        z_bottom,
        z_bottom,
        z_bottom,
        z_deck,
        z_deck,
        z_deck,
        z_deck,
    ]

    # Indici dei triangoli per formare le facce dello scafo
    i = [0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0]
    j = [1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4]
    k = [2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7]

    return x, y, z, i, j, k


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte (3D) — {selected_port}")
    st.caption(
        "📐 **Telemetro Laser:** Modifica solo Distanza e Pendenza. "
        "Le coordinate $X, Y, Z$ delle bitte si aggiornano automaticamente nello spazio 3D rispetto alle Observation Platform."
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

    # --- VISTA 3D NAVE & BANCHINA ---
    with col_map:
        st.subheader("🧊 Visualizzazione 3D Banchina e Nave")

        loa = ship_dict["LOA"]
        beam = ship_dict["Beam"]
        draft = ship_dict.get("Draft", 8.2)
        freeboard = ship_dict.get("Freeboard", 12.0)

        fig = go.Figure()

        # 1. Scafo Nave 3D Mesh
        sx, sy, sz, si, sj, sk = build_3d_ship_mesh(
            loa, beam, draft, freeboard
        )
        fig.add_trace(
            go.Mesh3d(
                x=sx,
                y=sy,
                z=sz,
                i=si,
                j=sj,
                k=sk,
                color="navy",
                opacity=0.35,
                name="Scafo Nave",
            )
        )

        # 2. Observation Platforms (Prua e Poppa)
        plat_fwd_x = (loa / 2.0) - OFFSET_PLATFORM_FWD_M
        plat_aft_x = (-loa / 2.0) + OFFSET_PLATFORM_AFT_M
        plat_z = freeboard + 2.0  # Quota ponte/piattaforma

        fig.add_trace(
            go.Scatter3d(
                x=[plat_fwd_x, plat_aft_x],
                y=[0, 0],
                z=[plat_z, plat_z],
                mode="markers+text",
                name="Observation Platforms",
                text=["Obs Fwd", "Obs Aft"],
                textposition="top center",
                marker=dict(size=8, color="gold", symbol="diamond"),
            )
        )

        # 3. Linea Banchina (Filo Banchina)
        berth_y = (beam / 2.0) + 6.4
        fig.add_trace(
            go.Scatter3d(
                x=[-loa, loa],
                y=[berth_y, berth_y],
                z=[0, 0],
                mode="lines",
                name="Filo Banchina",
                line=dict(color="black", width=4, dash="dash"),
            )
        )

        # 4. Bitte Calcolate in 3D
        fig.add_trace(
            go.Scatter3d(
                x=df_bollards["X_Coordinata_m"],
                y=df_bollards["Y_Coordinata_m"],
                z=df_bollards["Z_Altezza_m"],
                mode="markers+text",
                name="Bitte Banchina",
                text=df_bollards["bollard_id"],
                textposition="bottom center",
                marker=dict(size=6, color="red", symbol="square"),
            )
        )

        # Impostazioni Layout Scena 3D
        fig.update_layout(
            scene=dict(
                xaxis_title="X (m - Longitudinal)",
                yaxis_title="Y (m - Trasversale)",
                zaxis_title="Z (m - Verticale)",
                aspectmode="data",
                camera=dict(eye=dict(x=-1.5, y=-1.8, z=1.2)),
            ),
            height=550,
            margin=dict(l=0, r=0, b=0, t=30),
            showlegend=True,
        )

        st.plotly_chart(fig, use_container_width=True)
