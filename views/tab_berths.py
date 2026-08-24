"""
views/tab_berth.py
Layout banchina, bitte e calcolo da piattaforma osservazione (telemetro).
"""

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from config.constants import OFFSET_PLATFORM_AFT_M, OFFSET_PLATFORM_FWD_M


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte: {selected_port}")
    st.info(
        "📐 **Misurazione da Piattaforme d'Osservazione (Rangefinder):**\n"
        f"• **Observation Platform Prua:** posizionata a **{OFFSET_PLATFORM_FWD_M} m** dall'estrema prua.\n"
        f"• **Observation Platform Poppa:** posizionata a **{OFFSET_PLATFORM_AFT_M} m** dall'estrema poppa.\n"
        "Inserisci la **Distanza Inclinata (m)** e la **Pendenza (°)** rilevate con il telemetro."
    )

    loa = ship_dict["LOA"]
    beam = ship_dict["Beam"]

    st.subheader("⚙️ Orientamento Banchina")
    berth_heading = st.number_input(
        "Orientamento Banchina / Berth True Heading (° True)",
        min_value=0.0,
        max_value=360.0,
        value=float(st.session_state.port_headings.get(selected_port, 135.0)),
        step=1.0,
        key=f"heading_input_{selected_port}",
    )
    st.session_state.port_headings[selected_port] = berth_heading

    st.divider()

    df_bollards = st.session_state.ports_bollards[selected_port]

    st.subheader("➕ Aggiungi Nuova Bitta tramite Rilevamento Telemetro")
    c_add1, c_add2, c_add3, c_add4, c_add5, c_add6, c_add7 = st.columns(7)

    new_b_id = c_add1.text_input("ID Bitta", f"B{len(df_bollards) + 1}")
    new_pos = c_add2.selectbox(
        "Piattaforma Misura",
        ["Prua (21m fwd)", "Poppa (14m aft)"],
    )
    new_dist_inc = c_add3.number_input(
        "Dist. Inclinata (m)", min_value=0.0, value=15.0, step=0.5
    )
    new_pendenza = c_add4.number_input(
        "Pendenza (°)", min_value=-60.0, max_value=60.0, value=0.0, step=1.0
    )
    new_y = c_add5.number_input("Dist. Banchina Y (m)", value=25.0, step=0.5)
    new_z = c_add6.number_input("Altezza Z (m)", value=-3.0, step=0.5)
    new_swl = c_add7.number_input("SWL Bitta (t)", value=150, step=10)

    dist_horiz = new_dist_inc * math.cos(math.radians(new_pendenza))

    if "Prua" in new_pos:
        x_platform = (loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_abs_calc = x_platform - dist_horiz
        zone_label = "Prua"
    else:
        x_platform = -(loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_abs_calc = x_platform + dist_horiz
        zone_label = "Poppa"

    st.caption(
        f"💡 **Calcolo Anteprima:** Distanza Orizzontale = **{dist_horiz:.2f} m** | Coordinata X calcolata = **{x_abs_calc:.2f} m**"
    )

    if st.button("➕ Registra Bitta in Banchina"):
        new_row = {
            "bollard_id": new_b_id,
            "Posizione": zone_label,
            "Dist_Inclinata_m": new_dist_inc,
            "Pendenza_deg": new_pendenza,
            "Dist_Orizzontale_m": round(dist_horiz, 2),
            "X_Coordinata_m": round(x_abs_calc, 2),
            "Y_Coordinata_m": new_y,
            "Z_Altezza_m": new_z,
            "SWL_Bitta_t": new_swl,
            "Stato": "Attivo",
        }
        st.session_state.ports_bollards[selected_port] = pd.concat(
            [df_bollards, pd.DataFrame([new_row])], ignore_index=True
        )
        st.success(f"Bitta {new_b_id} aggiunta con successo!")
        st.rerun()

    st.divider()

    df_curr = st.session_state.ports_bollards[selected_port].copy()

    calc_dist_h, calc_x = [], []
    for _, r in df_curr.iterrows():
        d_inc = float(r.get("Dist_Inclinata_m", r.get("Dist_Estrema_m", 0.0)))
        pend = float(r.get("Pendenza_deg", 0.0))
        d_h = d_inc * math.cos(math.radians(pend))
        calc_dist_h.append(round(d_h, 2))

        pos = str(r.get("Posizione", "Prua"))
        if "Prua" in pos:
            x_plat = (loa / 2.0) - OFFSET_PLATFORM_FWD_M
            calc_x.append(round(x_plat - d_h, 2))
        else:
            x_plat = -(loa / 2.0) + OFFSET_PLATFORM_AFT_M
            calc_x.append(round(x_plat + d_h, 2))

    df_curr["Dist_Orizzontale_m"] = calc_dist_h
    df_curr["X_Coordinata_m"] = calc_x

    col_ed_left, col_ed_right = st.columns([1, 1])

    with col_ed_left:
        st.subheader("📋 Tabella Bitte Banchina")
        edited_bollards = st.data_editor(
            df_curr,
            num_rows="dynamic",
            use_container_width=True,
            key=f"editor_{selected_port}",
        )
        st.session_state.ports_bollards[selected_port] = edited_bollards

    with col_ed_right:
        st.subheader("🌐 Visualizzazione Layout 3D Banchina")

        fig_setup = go.Figure()
        s_x = [-loa / 2, loa / 2 - 30, loa / 2, loa / 2 - 30, -loa / 2, -loa / 2]
        s_y = [-beam / 2, -beam / 2, 0, beam / 2, beam / 2, -beam / 2]
        s_z = [10.0] * len(s_x)
        fig_setup.add_trace(
            go.Scatter3d(
                x=s_x,
                y=s_y,
                z=s_z,
                mode="lines",
                line=dict(color="navy", width=5),
                name="Scafo Nave",
            )
        )

        plat_x = [(loa / 2.0) - OFFSET_PLATFORM_FWD_M, -(loa / 2.0) + OFFSET_PLATFORM_AFT_M]
        plat_y = [beam / 2.0, beam / 2.0]
        plat_z = [12.0, 12.0]
        fig_setup.add_trace(
            go.Scatter3d(
                x=plat_x,
                y=plat_y,
                z=plat_z,
                mode="markers+text",
                marker=dict(size=10, color="crimson", symbol="diamond"),
                text=["Obs. Platform Prua (21m)", "Obs. Platform Poppa (14m)"],
                textposition="top center",
                name="Piattaforme Rilevamento",
            )
        )

        act_b = edited_bollards[edited_bollards["Stato"] == "Attivo"]
        fig_setup.add_trace(
            go.Scatter3d(
                x=act_b["X_Coordinata_m"],
                y=act_b["Y_Coordinata_m"],
                z=act_b["Z_Altezza_m"],
                mode="markers+text",
                marker=dict(
                    size=9,
                    color=act_b["SWL_Bitta_t"],
                    colorscale="Viridis",
                    showscale=True,
                ),
                text=[
                    f"{r['bollard_id']} ({r['Posizione']}: {r['Dist_Orizzontale_m']}m h-dist,"
                    f" SWL:{r['SWL_Bitta_t']}t)"
                    for _, r in act_b.iterrows()
                ],
                textposition="top center",
                name="Bitte Banchina",
            )
        )

        fig_setup.update_layout(
            scene=dict(
                aspectmode="data",
                xaxis_title="X (m)",
                yaxis_title="Y (m)",
                zaxis_title="Z (m)",
            ),
            margin=dict(l=0, r=0, b=0, t=30),
            height=520,
        )
        st.plotly_chart(fig_setup, use_container_width=True)
