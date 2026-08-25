"""
views/tab_berth.py
Modulo avanzato per la gestione del layout di banchina e visualizzazione 3D completa della nave.
Sfrutta tutti i dati geometrici e propulsivi centralizzati in DEFAULT_SHIP.
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


def generate_detailed_3d_ship(ship_dict):
    """Genera la struttura 3D dettagliata della nave utilizzando tutti i parametri disponibili."""
    # Estrazione parametri principali
    loa = ship_dict.get("LOA", 323.44)
    beam_hull = ship_dict.get("Beam", 37.20)
    beam_max = ship_dict.get("Beam_Max", 49.40)
    draft = ship_dict.get("Draft", 8.25)
    freeboard = ship_dict.get("Freeboard", 2.65)
    air_draft_funnel = ship_dict.get("Air_Draft_Funnel", 61.75)
    air_draft_mast = ship_dict.get("Air_Draft_Mast", 63.25)
    bridge_bow = ship_dict.get("Bridge_To_Bow", 39.50)
    bridge_eye_h = ship_dict.get("Bridge_Eye_Height", 26.40)

    loa_half = loa / 2.0
    beam_half = beam_hull / 2.0
    deck_main_z = freeboard  # Altezza ponte principale rispetto al galleggiamento

    traces = []

    # ----------------------------------------------------
    # 1. CARENA E IMPERMEABILE SUBACQUEO (Pescaggio)
    # ----------------------------------------------------
    hull_sub_x = [
        -loa_half * 0.95,
        loa_half * 0.75,
        loa_half * 0.9,
        loa_half * 0.75,
        -loa_half * 0.95,
        -loa_half * 0.95,
    ]
    hull_sub_y = [
        -beam_half * 0.9,
        -beam_half * 0.9,
        0,
        beam_half * 0.9,
        beam_half * 0.9,
        -beam_half * 0.9,
    ]
    hull_sub_z = [-draft] * len(hull_sub_x)

    traces.append(
        go.Scatter3d(
            x=hull_sub_x,
            y=hull_sub_y,
            z=hull_sub_z,
            mode="lines",
            line=dict(color="darkred", width=5),
            name=f"Carena / Pescaggio ({draft}m)",
        )
    )

    # Bulbo di Prua (Bulbous Bow)
    traces.append(
        go.Scatter3d(
            x=[loa_half * 0.85, loa_half * 0.98, loa_half * 0.85],
            y=[0, 0, 0],
            z=[-draft, -draft * 0.5, 0],
            mode="lines+markers",
            line=dict(color="crimson", width=6),
            marker=dict(size=4, color="crimson"),
            name="Bulbo di Prua",
        )
    )

    # ----------------------------------------------------
    # 2. SCAFO PRINCIPALE (Ponte di Coperta & Bordo Libero)
    # ----------------------------------------------------
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
    hull_z = [deck_main_z] * len(hull_x)

    traces.append(
        go.Scatter3d(
            x=hull_x,
            y=hull_y,
            z=hull_z,
            mode="lines",
            line=dict(color="navy", width=7),
            name=f"Scafo Fuori Acqua (Bordo Libero {freeboard}m)",
        )
    )

    # ----------------------------------------------------
    # 3. SOVRASTRUTTURA PONTI PASSEGGERI (Hotel Block)
    # ----------------------------------------------------
    # Blocco Inferiore (Ponti Cabine)
    super_lower_x = [
        -loa_half * 0.88,
        loa_half * 0.65,
        loa_half * 0.65,
        -loa_half * 0.88,
        -loa_half * 0.88,
    ]
    super_lower_y = [
        -beam_half * 0.95,
        -beam_half * 0.95,
        beam_half * 0.95,
        beam_half * 0.95,
        -beam_half * 0.95,
    ]
    super_lower_z = [18.0] * 5

    traces.append(
        go.Scatter3d(
            x=super_lower_x,
            y=super_lower_y,
            z=super_lower_z,
            mode="lines",
            line=dict(color="royalblue", width=4),
            name="Ponti Passeggeri (Inferiori)",
        )
    )

    # Blocco Superiore (Lido & Ponti Solarium)
    super_upper_x = [
        -loa_half * 0.75,
        loa_half * 0.55,
        loa_half * 0.55,
        -loa_half * 0.75,
        -loa_half * 0.75,
    ]
    super_upper_y = [
        -beam_half * 0.85,
        -beam_half * 0.85,
        beam_half * 0.85,
        beam_half * 0.85,
        -beam_half * 0.85,
    ]
    super_upper_z = [38.0] * 5

    traces.append(
        go.Scatter3d(
            x=super_upper_x,
            y=super_upper_y,
            z=super_upper_z,
            mode="lines",
            line=dict(color="steelblue", width=4),
            name="Ponte Lido & Solarium",
        )
    )

    # ----------------------------------------------------
    # 4. PLANCIA DI COMANDO E ALETTE SPORGENTI (Beam Max)
    # ----------------------------------------------------
    bridge_x_pos = loa_half - bridge_bow
    wing_y_half = beam_max / 2.0

    # Linea Alette di Plancia
    traces.append(
        go.Scatter3d(
            x=[bridge_x_pos, bridge_x_pos],
            y=[-wing_y_half, wing_y_half],
            z=[bridge_eye_h, bridge_eye_h],
            mode="lines+markers",
            line=dict(color="darkred", width=8),
            marker=dict(size=6, color="red"),
            name=f"Plancia & Alette ({beam_max}m - Eye Height {bridge_eye_h}m)",
        )
    )

    # Struttura Vetrata della Plancia
    traces.append(
        go.Scatter3d(
            x=[
                bridge_x_pos,
                bridge_x_pos + 3.0,
                bridge_x_pos,
                bridge_x_pos,
            ],
            y=[-wing_y_half, 0, wing_y_half, -wing_y_half],
            z=[bridge_eye_h, bridge_eye_h + 1.5, bridge_eye_h, bridge_eye_h],
            mode="lines",
            line=dict(color="cyan", width=3),
            name="Vetrata Plancia",
        )
    )

    # ----------------------------------------------------
    # 5. FUMAIOLO & ALBERO ANTENNE (Air Draft)
    # ----------------------------------------------------
    funnel_z_top = air_draft_funnel - draft
    mast_z_top = air_draft_mast - draft

    # Fumaiolo Caratteristico
    traces.append(
        go.Scatter3d(
            x=[-15, 5, -5, -25, -15],
            y=[0, 0, 0, 0, 0],
            z=[38.0, 38.0, funnel_z_top, funnel_z_top, 38.0],
            mode="lines",
            line=dict(color="crimson", width=9),
            name=f"Fumaiolo (Air Draft {air_draft_funnel}m)",
        )
    )

    # Albero Antenne (Main Mast)
    traces.append(
        go.Scatter3d(
            x=[bridge_x_pos - 10, bridge_x_pos - 10],
            y=[0, 0],
            z=[38.0, mast_z_top],
            mode="lines+markers",
            line=dict(color="gold", width=5),
            marker=dict(size=4, color="gold"),
            name=f"Albero Antenne (Air Draft {air_draft_mast}m)",
        )
    )

    # ----------------------------------------------------
    # 6. PLATFORMS DI OSSERVAZIONE (Obs Fwd & Obs Aft)
    # ----------------------------------------------------
    plat_fwd_x = loa_half - OFFSET_PLATFORM_FWD_M
    plat_aft_x = -loa_half + OFFSET_PLATFORM_AFT_M

    traces.append(
        go.Scatter3d(
            x=[plat_fwd_x, plat_aft_x],
            y=[0, 0],
            z=[deck_main_z + 2.0, deck_main_z + 2.0],
            mode="markers+text",
            name="Observation Platforms",
            text=[f"Obs Fwd (-{OFFSET_PLATFORM_FWD_M}m)", f"Obs Aft (-{OFFSET_PLATFORM_AFT_M}m)"],
            textposition="top center",
            marker=dict(size=9, color="gold", symbol="diamond"),
        )
    )

    # ----------------------------------------------------
    # 7. MANOVRA E PROPULSIONE (Thrusters & Azipods)
    # ----------------------------------------------------
    # Bow Thrusters (3 Tunnel a prua)
    thruster_x = [loa_half * 0.68, loa_half * 0.72, loa_half * 0.76]
    for i, tx in enumerate(thruster_x):
        traces.append(
            go.Scatter3d(
                x=[tx, tx],
                y=[-beam_half * 0.8, beam_half * 0.8],
                z=[-draft * 0.6, -draft * 0.6],
                mode="lines",
                line=dict(color="orange", width=4, dash="dot"),
                name=f"Bow Thruster #{i+1}" if i == 0 else "",
                showlegend=(i == 0),
            )
        )

    # Azipods (2 Unità orientabili a poppa)
    azipod_x = -loa_half * 0.85
    traces.append(
        go.Scatter3d(
            x=[azipod_x, azipod_x, azipod_x, azipod_x],
            y=[-beam_half * 0.4, -beam_half * 0.4, beam_half * 0.4, beam_half * 0.4],
            z=[-draft, -draft - 2.5, -draft, -draft - 2.5],
            mode="lines+markers",
            line=dict(color="purple", width=6),
            marker=dict(size=6, color="purple"),
            name=f"2x Azipods ({ship_dict.get('Azipods_Power_kW', 33000)} kW)",
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

    # Ricalcolo coordinate bitte basato sugli offset
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

        # Tabella Carico Vento
        if "Wind_Load_Table" in ship_dict:
            st.markdown("**🌬️ Carico Vento Stimato dalla Curva Tecnica:**")
            w_df = pd.DataFrame(
                list(ship_dict["Wind_Load_Table"].items()),
                columns=["Vento (Nodi)", "Spinta Trasversale Totale (Tons)"],
            )
            st.table(w_df)

    with col_map:
        st.subheader("🧊 Modellazione 3D Completa")

        fig = go.Figure()

        # 1. Tracciamento Modello Dettagliato Nave 3D
        ship_traces = generate_detailed_3d_ship(ship_dict)
        for trace in ship_traces:
            fig.add_trace(trace)

        # 2. Modellazione Banchina 3D (Banchina parallela a dritta)
        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)
        berth_y = (beam / 2.0) + 6.4

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

        # 3. Positionamento Bitte Banchina
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

        # Impostazioni Camera e Layout Prospettico
        fig.update_layout(
            scene=dict(
                xaxis_title="X / Lunghezza (m)",
                yaxis_title="Y / Larghezza (m)",
                zaxis_title="Z / Altezza (m)",
                aspectmode="data",
                camera=dict(
                    eye=dict(x=-1.6, y=-1.6, z=1.2),
                    center=dict(x=0, y=0, z=10),
                ),
            ),
            height=620,
            margin=dict(l=0, r=0, b=0, t=30),
        )

        st.plotly_chart(fig, use_container_width=True)
