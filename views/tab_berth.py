"""
views/tab_berth.py
Modulo per la gestione del layout di banchina e posizionamento bitte
tramite telemetro (Distanza e Pendenza da Observation Platform).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """Calcola le coordinate X, Y, Z della bitta partendo da Distanza e Pendenza

    misurate dalle Observation Platform di Prua / Poppa.
    """
    slope_rad = np.radians(slope_deg)

    # 1. Distanza orizzontale e offset verticale Z
    dist_horiz = dist_inc * np.cos(slope_rad)
    z_m = -1.0 * (dist_inc * np.sin(slope_rad))

    # 2. Coordinata X basata sulle piattaforme di osservazione
    if position_type == "Prua":
        # Platform Prua = LOA/2 - OFFSET_PLATFORM_FWD_M (21m)
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_m = x_platform - dist_horiz
    else:
        # Platform Poppa = -LOA/2 + OFFSET_PLATFORM_AFT_M (14m)
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_m = x_platform + dist_horiz

    # 3. Coordinata Y (distanza fissa filo banchina/bitta dal centro nave)
    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte — {selected_port}")
    st.caption(
        "📐 **Telemetro Laser:** Inserisci solo Distanza e Pendenza. "
        "Le coordinate $X, Y, Z$ vengono calcolate automaticamente dalle Observation Platform."
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcolo automatico di X, Y, Z per ogni bitta nel DataFrame
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

    # Editor semplificato: mostra e fa modificare SOLO Distanza e Pendenza
    col_edit, col_map = st.columns([1, 1])

    with col_edit:
        st.subheader("📋 Inserimento Misure Telemetro")

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
                    "Stazione / Posizione",
                    options=["Prua", "Poppa"],
                    required=True,
                ),
                "Dist_Inclinata_m": st.column_config.NumberColumn(
                    "Distanza Telemetro (m)",
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

        # Salva le modifiche nell'inventario di sessione
        if st.button("💾 Aggiorna Layout Bitte"):
            # Applica nuovamente il calcolo per salvare le coordinate finali
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
            st.success("Layout banchina aggiornato con successo!")
            st.rerun()

    # Mappa 2D del Layout Nave-Banchina
    with col_map:
        st.subheader("📍 Visualizzazione 2D Banchina")
        fig = go.Figure()

        # Profilo della Nave
        loa = ship_dict["LOA"]
        beam = ship_dict["Beam"]
        ship_x = [-loa / 2, loa / 2, loa / 2, -loa / 2, -loa / 2]
        ship_y = [-beam / 2, -beam / 2, beam / 2, beam / 2, -beam / 2]

        fig.add_trace(
            go.Scatter(
                x=ship_x,
                y=ship_y,
                fill="toself",
                name="Carnival Panorama",
                line=dict(color="navy"),
            )
        )

        # Observation Platforms
        plat_fwd_x = (loa / 2) - OFFSET_PLATFORM_FWD_M
        plat_aft_x = (-loa / 2) + OFFSET_PLATFORM_AFT_M

        fig.add_trace(
            go.Scatter(
                x=[plat_fwd_x, plat_aft_x],
                y=[0, 0],
                mode="markers+text",
                name="Observation Platforms",
                text=["Obs Fwd (21m)", "Obs Aft (14m)"],
                textposition="top center",
                marker=dict(size=10, color="orange", symbol="star"),
            )
        )

        # Posizione delle Bitte Calcolate
        fig.add_trace(
            go.Scatter(
                x=df_bollards["X_Coordinata_m"],
                y=df_bollards["Y_Coordinata_m"],
                mode="markers+text",
                name="Bitte Banchina",
                text=df_bollards["bollard_id"],
                textposition="bottom center",
                marker=dict(size=12, color="red", symbol="square"),
            )
        )

        fig.update_layout(
            xaxis_title="X (m dall'ordinata maestra)",
            yaxis_title="Y (m dal centro nave)",
            height=450,
            showlegend=True,
        )
        st.plotly_chart(fig, use_container_width=True)
