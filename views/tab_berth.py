"""
views/tab_berth.py
Modulo per la gestione del layout di banchina:
- Modellazione 3D stilizzata della nave attingendo ai dati centralizzati
- Banchina 3D e posizionamento relativo alle Observation Platforms (Prua 25m, Poppa 14m)
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """Calcola le coordinate X, Y, Z della bitta rispetto alle Observation Platforms."""
    slope_rad = np.radians(slope_deg)

    dist_horiz = dist_inc * np.cos(slope_rad)
    z_m = -1.0 * (dist_inc * np.sin(slope_rad))

    if position_type == "Prua":
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M  # 25m da prua
        x_m = x_platform - dist_horiz
    else:
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M  # 14m da poppa
        x_m = x_platform + dist_horiz

    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def generate_stylized_cruise_ship(ship_dict):
    """Genera la struttura 3D della nave dai dati centralizzati in ship_dict."""
    loa = ship_dict.get("LOA", 323.44)
    beam_hull = ship_dict.get("Beam", 37.20)
    beam_max = ship_dict.get("Beam_Max", 49.40)
    air_draft = ship_dict.get("Air_Draft_Funnel", 61.75)
    draft = ship_dict.get("Draft", 8.25)
    bridge_bow = ship_dict.get("Bridge_To_Bow", 39.50)

    loa_half = loa / 2.0
    beam_half = beam_hull / 2.0

    traces = []

    # 1. Scafo con prua a cuneo
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
    hull_z = [12.0] * len(hull_x)

    traces.append(
        go.Scatter3d(
            x=hull_x,
            y=hull_y,
            z=hull_z,
            mode="lines",
            line=dict(color="navy", width=6),
            name="Scafo (Ponte Principale)",
        )
    )

    # 2. Sovrastruttura ponti passeggeri
    super_x = [
        -loa_half * 0.85,
        loa_half * 0.65,
        loa_half * 0.65,
        -loa_half * 0.85,
        -loa_half * 0.85,
    ]
    super_y = [
        -beam_half * 0.9,
        -beam_half * 0.9,
        beam_half * 0.9,
        beam_half * 0.9,
        -beam_half * 0.9,
    ]
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

    # 3. Alette di Plancia
    bridge_x_pos = loa_half - bridge_bow
    wing_y_half = beam_max / 2.0
    traces.append(
        go.Scatter3d(
            x=[bridge_x_pos, bridge_x_pos],
            y=[-wing_y_half, wing_y_half],
            z=[38.0, 38.0],
            mode="lines+markers",
            line=dict(color="red", width=6),
            marker=dict(size=5, color="red"),
            name=f"Plancia & Alette ({beam_max}m)",
        )
    )

    # 4. Fumaiolo
    funnel_z_top = air_draft - draft
    traces.append(
        go.Scatter3d(
            x=[-10, 10, 0, -10],
            y=[0, 0, 0, 0],
            z=[35.0, 35.0, funnel_z_top, 35.0],
            mode="lines",
            line=dict(color="crimson", width=8),
            name="Fumaiolo",
        )
    )

    # 5. Observation Platforms (Prua -25m, Poppa -14m)
    plat_fwd_x = loa_half - OFFSET_PLATFORM_FWD_M
    plat_aft_x = -loa_half + OFFSET_PLATFORM_AFT_M

    traces.append(
        go.Scatter3d(
            x=[plat_fwd_x, plat_aft_x],
            y=[0, 0],
            z=[12.0, 12.0],
            mode="markers+text",
            name="Observation Platforms",
            text=["Obs Fwd (-25m)", "Obs Aft (-14m)"],
            textposition="top center",
            marker=dict(size=8, color="gold", symbol="diamond"),
        )
    )

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina 3D — {selected_port}")
    st.caption(
        f"🚢 Nave selezionata: **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** | "
        f"Obs Fwd: **-{OFFSET_PLATFORM_FWD_M}m** | Obs Aft: **-{OFFSET_PLATFORM_AFT_M}m**"
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcolo coordinate bitte con i nuovi offset
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
            st.success("Layout aggiornato con i nuovi offset!")
            st.rerun()

        if "Wind_Load_Table" in ship_dict:
            st.markdown("**🌬️ Carico Vento Stimato (Wind Load Table):**")
            w_df = pd.DataFrame(
                list(ship_dict["Wind_Load_Table"].items()),
                columns=["Wind Speed (Kts)", "Total Load (Tons)"],
            )
            st.table(w_df)

    with col_map:
        st.subheader("🧊 Vista 3D Banchina & Nave")

        fig = go.Figure()

        # 1. Modellazione 3D della nave
        ship_traces = generate_stylized_cruise_ship(ship_dict)
        for trace in ship_traces:
            fig.add_trace(trace)

        # 2. Struttura Banchina 3D
        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)
        berth_y = (beam / 2.0) + 6.4

        fig.add_trace(
            go.Mesh3d(
                x=[
                    -loa * 0.6,
                    loa * 0.6,
                    loa * 0.6,
                    -loa * 0.6,
                    -loa * 0.6,
                    loa * 0.6,
                    loa * 0.6,
                    -loa * 0.6,
                ],
                y=[
                    berth_y,
                    berth_y,
                    berth_y + 12,
                    berth_y + 12,
                    berth_y,
                    berth_y,
                    berth_y + 12,
                    berth_y + 12,
                ],
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
