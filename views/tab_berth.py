"""
views/tab_berth.py
Modulo per la gestione del layout di banchina e modellazione 3D volumetrica della nave.
Costruisce lo scafo 3D (Mesh3d), la sovrastruttura, la banchina, le bitte e i cavi d'ormeggio.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.line_mechanics import calculate_line_geometry

# Offset fisso delle piattaforme di osservazione rispetto agli estremi
OFFSET_PLATFORM_FWD_M = 25.0
OFFSET_PLATFORM_AFT_M = 14.0


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


def generate_detailed_3d_ship(ship_dict):
    """Genera lo scafo volumetrico 3D (Mesh3d) e la sovrastruttura tridimensionale della nave."""
    loa = ship_dict.get("LOA", 323.44)
    beam_hull = ship_dict.get("Beam", 37.20)
    beam_max = ship_dict.get("Beam_Max", 49.40)
    draft = ship_dict.get("Draft", 8.25)
    freeboard = ship_dict.get("Freeboard", 2.65)
    air_draft_funnel = ship_dict.get("Air_Draft_Funnel", 61.75)
    bridge_bow = ship_dict.get("Bridge_To_Bow", 39.50)
    bridge_eye_h = ship_dict.get("Bridge_Eye_Height", 26.40)

    loa_half = loa / 2.0
    beam_half = beam_hull / 2.0
    deck_z = freeboard  # Quota ponte principale (m)
    bottom_z = -draft  # Quota chiglia (m)

    traces = []

    # ----------------------------------------------------
    # 1. SCAFO VOLUMETRICO 3D (SOLIDO MESH3D)
    # ----------------------------------------------------
    x_v = [
        -loa_half,
        loa_half * 0.7,
        loa_half,
        loa_half * 0.7,
        -loa_half,
        -loa_half,
        loa_half * 0.7,
        loa_half,
        loa_half * 0.7,
        -loa_half,
    ]
    y_v = [
        -beam_half,
        -beam_half,
        0,
        beam_half,
        beam_half,
        -beam_half,
        -beam_half,
        0,
        beam_half,
        beam_half,
    ]
    z_v = [deck_z] * 5 + [bottom_z] * 5

    i_faces = [0, 0, 0, 0, 5, 5, 0, 1, 1, 2, 2, 3, 3, 4]
    j_faces = [1, 2, 3, 4, 6, 7, 5, 6, 2, 7, 3, 8, 4, 9]
    k_faces = [2, 3, 4, 1, 7, 8, 1, 2, 7, 3, 8, 4, 9, 5]

    traces.append(
        go.Mesh3d(
            x=x_v,
            y=y_v,
            z=z_v,
            i=i_faces,
            j=j_faces,
            k=k_faces,
            color="navy",
            opacity=0.85,
            name="Scafo Solido 3D",
        )
    )

    # ----------------------------------------------------
    # 2. SOVRASTRUTTURA PONTI 3D
    # ----------------------------------------------------
    sup_z_bottom = deck_z
    sup_z_top = 35.0
    x_s = [
        -loa_half * 0.85,
        loa_half * 0.65,
        loa_half * 0.65,
        -loa_half * 0.85,
        -loa_half * 0.85,
        loa_half * 0.65,
        loa_half * 0.65,
        -loa_half * 0.85,
    ]
    y_s = [
        -beam_half * 0.9,
        -beam_half * 0.9,
        beam_half * 0.9,
        beam_half * 0.9,
        -beam_half * 0.9,
        -beam_half * 0.9,
        beam_half * 0.9,
        beam_half * 0.9,
    ]
    z_s = [sup_z_bottom] * 4 + [sup_z_top] * 4

    traces.append(
        go.Mesh3d(
            x=x_s,
            y=y_s,
            z=z_s,
            i=[0, 0, 0, 1, 2, 3, 4, 4, 0, 1, 2, 3],
            j=[1, 2, 4, 5, 6, 7, 5, 6, 3, 2, 6, 7],
            k=[2, 3, 5, 6, 7, 4, 6, 7, 4, 5, 1, 0],
            color="royalblue",
            opacity=0.75,
            name="Sovrastruttura Ponti 3D",
        )
    )

    # ----------------------------------------------------
    # 3. PLANCIA DI COMANDO & ALETTE (BEAM MAX)
    # ----------------------------------------------------
    bridge_x = loa_half - bridge_bow
    wing_y = beam_max / 2.0

    traces.append(
        go.Scatter3d(
            x=[bridge_x, bridge_x],
            y=[-wing_y, wing_y],
            z=[bridge_eye_h, bridge_eye_h],
            mode="lines+markers",
            line=dict(color="red", width=8),
            marker=dict(size=6, color="red"),
            name=f"Plancia & Alette ({beam_max}m)",
        )
    )

    # ----------------------------------------------------
    # 4. FUMAIOLO & OBSERVATION PLATFORMS
    # ----------------------------------------------------
    funnel_z = air_draft_funnel - draft
    traces.append(
        go.Scatter3d(
            x=[-15, 5, -5, -25, -15],
            y=[0, 0, 0, 0, 0],
            z=[sup_z_top, sup_z_top, funnel_z, funnel_z, sup_z_top],
            mode="lines",
            line=dict(color="crimson", width=8),
            name=f"Fumaiolo ({air_draft_funnel}m)",
        )
    )

    plat_fwd_x = loa_half - OFFSET_PLATFORM_FWD_M
    plat_aft_x = -loa_half + OFFSET_PLATFORM_AFT_M

    traces.append(
        go.Scatter3d(
            x=[plat_fwd_x, plat_aft_x],
            y=[0, 0],
            z=[deck_z + 2.0, deck_z + 2.0],
            mode="markers+text",
            name="Observation Platforms",
            text=[
                f"Obs Fwd (-{OFFSET_PLATFORM_FWD_M}m)",
                f"Obs Aft (-{OFFSET_PLATFORM_AFT_M}m)",
            ],
            textposition="top center",
            marker=dict(size=10, color="gold", symbol="diamond"),
        )
    )

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Modello 3D Nave — {selected_port}")
    st.caption(
        f"🚢 **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** | "
        f"Baglio Max: **{ship_dict.get('Beam_Max')}m** | Air Draft: **{ship_dict.get('Air_Draft_Mast')}m** | "
        f"Obs Fwd: **-{OFFSET_PLATFORM_FWD_M}m** | Obs Aft: **-{OFFSET_PLATFORM_AFT_M}m**"
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

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

    with col_edit:
        st.subheader("📋 Telemetro Laser & Dati Carico Vento")

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
            st.success("Layout e coordinate ricalcolate!")
            st.rerun()

        if "Wind_Load_Table" in ship_dict:
            st.markdown("**🌬️ Carico Vento Stimato dalla Curva Tecnica:**")
            w_df = pd.DataFrame(
                list(ship_dict["Wind_Load_Table"].items()),
                columns=["Vento (Nodi)", "Spinta Trasversale Totale (Tons)"],
            )
            st.table(w_df)

    with col_map:
        st.subheader("🧊 Modellazione 3D Volumetrica")

        fig = go.Figure()

        # Genera e aggiunge la geometria della nave
        ship_traces = generate_detailed_3d_ship(ship_dict)
        for trace in ship_traces:
            fig.add_trace(trace)

        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)
        berth_y = (beam / 2.0) + 6.4

        # Aggiunge la Banchina
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
                    berth_y,
                    berth_y,
                    berth_y + 15,
                    berth_y + 15,
                    berth_y,
                    berth_y,
                    berth_y + 15,
                    berth_y + 15,
                ],
                z=[-6, -6, -6, -6, 0, 0, 0, 0],
                i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0],
                j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                color="slategrey",
                opacity=0.5,
                name="Struttura Banchina (Z=0m)",
            )
        )

        # Aggiunge le Bitte
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

        # Calcola e Disegna i Cavi d'Ormeggio se presenti in session_state
        if "lines_inventory" in st.session_state and not st.session_state.lines_inventory.empty:
            geom_df = calculate_line_geometry(
                st.session_state.lines_inventory,
                df_bollards,
                loa=loa
            )
            if not geom_df.empty:
                for _, line in geom_df.iterrows():
                    fig.add_trace(
                        go.Scatter3d(
                            x=[line["chock_x_m"], line["bollard_x_m"]],
                            y=[line["chock_y_m"], line["bollard_y_m"]],
                            z=[line["chock_z_m"], line["bollard_z_m"]],
                            mode="lines",
                            line=dict(color="orange", width=4),
                            name=f"Cavo {line.get('line_id', '')}",
                            showlegend=False
                        )
                    )

        # Configurazione del Layout e Centratura della Telecamera attorno a (0,0,0)
        fig.update_layout(
            scene=dict(
                xaxis=dict(range=[-loa / 2.0 - 40, loa / 2.0 + 40], title="X / Longitudinale (m)"),
                yaxis=dict(range=[-beam, berth_y + 20], title="Y / Trasversale (m)"),
                zaxis=dict(range=[-12, 50], title="Z / Verticale (m)"),
                aspectmode="data",
                camera=dict(
                    center=dict(x=0, y=0, z=0),  # Mantiene il perno di rotazione perfettamente centrato
                    eye=dict(x=1.3, y=-1.3, z=0.9),
                ),
            ),
            height=650,
            margin=dict(l=0, r=0, b=0, t=30),
        )

        st.plotly_chart(fig, use_container_width=True)
