"""
views/tab_berth.py
Modulo per la gestione del layout di banchina:
- Modellazione 3D stilizzata della Carnival Horizon / Vista 3D avanzata
- Banchina 3D (Z=0) e Nave 3D posizionata alla quota di galleggiamento corretta
- Integrazione dati da Pilot Card e Wind Load
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M

# Dati tecnici estratti dalla Pilot Card (Carnival Horizon / Panorama Class)
SHIP_LOA = 323.44
SHIP_BEAM_HULL = 37.20
SHIP_BEAM_MAX = 49.40  # Alette di plancia
SHIP_DRAFT = 8.25
SHIP_AIR_DRAFT = 61.75  # Fino al fumaiolo
BRIDGE_TO_BOW = 39.50


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """Calcola le coordinate X, Y, Z della bitta rispetto alle Observation Platforms."""
    slope_rad = np.radians(slope_deg)

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


def generate_stylized_cruise_ship():
    """Genera i componenti tridimensionali stilizzati della nave da crociera."""
    loa_half = SHIP_LOA / 2.0
    beam_half = SHIP_BEAM_HULL / 2.0

    traces = []

    # 1. Scafo (Prua affilata + Poppa squadrata)
    hull_x = [
        -loa_half,
        loa_half * 0.7,
        loa_half,
        loa_half * 0.7,
        -loa_half,
        -loa_half,
    ]
    hull_y = [
        -beam_half,
        -beam_half,
        0,
        beam_half,
        beam_half,
        -beam_half,
    ]
    hull_z_base = [0] * len(hull_x)
    hull_z_deck = [12.0] * len(hull_x)

    traces.append(
        go.Scatter3d(
            x=hull_x,
            y=hull_y,
            z=hull_z_deck,
            mode="lines",
            line=dict(color="darkblue", width=6),
            name="Scafo (Ponte Principale)",
        )
    )

    # 2. Sovrastruttura (Ponti Passeggeri)
    super_x = [-loa_half * 0.85, loa_half * 0.65, loa_half * 0.65, -loa_half * 0.85, -loa_half * 0.85]
    super_y = [-beam_half * 0.9, -beam_half * 0.9, beam_half * 0.9, beam_half * 0.9, -beam_half * 0.9]
    super_z = [35.0] * 5

    traces.append(
        go.Scatter3d(
            x=super_x,
            y=super_y,
            z=super_z,
            mode="lines",
            line=dict(color="royalblue", width=4),
            name="Sovrastruttura Ponti",
        )
    )

    # 3. Alette di Plancia Estese (Max Breadth = 49.4m)
    bridge_x_pos = loa_half - BRIDGE_TO_BOW
    wing_y_half = SHIP_BEAM_MAX / 2.0
    traces.append(
        go.Scatter3d(
            x=[bridge_x_pos, bridge_x_pos],
            y=[-wing_y_half, wing_y_half],
            z=[38.0, 38.0],
            mode="lines+markers",
            line=dict(color="red", width=6),
            marker=dict(size=5, color="red"),
            name="Plancia & Alette (49.4m)",
        )
    )

    # 4. Fumaiolo
    funnel_x = [-10, 10, 0, -10]
    funnel_y = [0, 0, 0, 0]
    funnel_z = [35.0, 35.0, SHIP_AIR_DRAFT - SHIP_DRAFT, 35.0]
    traces.append(
        go.Scatter3d(
            x=funnel_x,
            y=funnel_y,
            z=funnel_z,
            mode="lines",
            line=dict(color="crimson", width=8),
            name="Fumaiolo Stilo",
        )
    )

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina 3D — {selected_port}")
    st.caption(
        f"🚢 Modello 3D basato sui dati tecnici della Pilot Card (LOA {SHIP_LOA}m, "
        f"Alette Plancia {SHIP_BEAM_MAX}m, Air Draft {SHIP_AIR_DRAFT}m)."
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcolo coordinate
    z_offsets = []
    for idx, row in df_bollards.iterrows():
        pos = row.get("Posizione", "Prua")
        d_inc = float(row.get("Dist_Inclinata_m", 15.0))
        p_deg = float(row.get("Pendenza_deg", 0.0))

        d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
            pos, d_inc, p_deg, SHIP_LOA, SHIP_BEAM_HULL
        )

        df_bollards.at[idx, "Dist_Orizzontale_m"] = d_horiz
        df_bollards.at[idx, "X_Coordinata_m"] = x_calc
        df_bollards.at[idx, "Y_Coordinata_m"] = y_calc
        df_bollards.at[idx, "Z_Altezza_m"] = z_calc
        df_bollards.at[idx, "bollard_x_m"] = x_calc
        df_bollards.at[idx, "bollard_y_m"] = y_calc
        df_bollards.at[idx, "bollard_z_m"] = z_calc
        z_offsets.append(abs(z_calc))

    col_edit, col_map = st.columns([1, 1.2])

    with col_edit:
        st.subheader("📋 Telemetro Laser & Carico Vento")

        edited_df = st.data_editor(
            df_bollards[[
                "bollard_id",
                "Posizione",
                "Dist_Inclinata_m",
                "Pendenza_deg",
                "SWL_Bitta_t",
                "Stato",
            ]],
            hide_index=True,
            use_container_width=True,
        )

        if st.button("💾 Aggiorna Layout"):
            st.session_state.ports_bollards[selected_port] = edited_df
            st.success("Layout aggiornato!")
            st.rerun()

        # Tabella di riferimento Wind Load estratta dal grafico
        st.markdown("**🌬️ Carico Vento Stimato (Wind Load Table):**")
        st.table(
            pd.DataFrame({
                "Wind Speed (Kts)": [15, 20, 25, 30],
                "Total Load (Tons)": [42, 69, 112, 155],
            })
        )

    with col_map:
        st.subheader("🧊 Vista 3D Banchina & Nave")

        fig = go.Figure()

        # 1. Tracce Modello Nave Stilizzata
        ship_traces = generate_stylized_cruise_ship()
        for trace in ship_traces:
            fig.add_trace(trace)

        # 2. Banchina 3D
        berth_y = (SHIP_BEAM_HULL / 2.0) + 6.4
        fig.add_trace(
            go.Mesh3d(
                x=[-SHIP_LOA * 0.6, SHIP_LOA * 0.6, SHIP_LOA * 0.6, -SHIP_LOA * 0.6, -SHIP_LOA * 0.6, SHIP_LOA * 0.6, SHIP_LOA * 0.6, -SHIP_LOA * 0.6],
                y=[berth_y, berth_y, berth_y + 12, berth_y + 12, berth_y, berth_y, berth_y + 12, berth_y + 12],
                z=[-5, -5, -5, -5, 0, 0, 0, 0],
                i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0],
                j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                color="slategrey",
                opacity=0.6,
                name="Banchina (Z=0)",
            )
        )

        # 3. Bitte sulla Banchina
        fig.add_trace(
            go.Scatter3d(
                x=df_bollards["X_Coordinata_m"],
                y=df_bollards["Y_Coordinata_m"],
                z=[0.0] * len(df_bollards),
                mode="markers+text",
                name="Bitte Banchina",
                text=df_bollards["bollard_id"],
                textposition="bottom center",
                marker=dict(size=7, color="red", symbol="square"),
            )
        )

        fig.update_layout(
            scene=dict(
                xaxis_title="X (m)",
                yaxis_title="Y (m)",
                zaxis_title="Z (m)",
                aspectmode="data",
                camera=dict(eye=dict(x=-1.5, y=-1.5, z=1.1)),
            ),
            height=580,
            margin=dict(l=0, r=0, b=0, t=30),
        )

        st.plotly_chart(fig, use_container_width=True)
