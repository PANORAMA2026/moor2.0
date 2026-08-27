"""
views/tab_berth.py
Gestione layout banchina, aggiunta dinamica bitte con riferimento differenziato Prua/Poppa,
congelamento (Fixed Anchor Points) e Modellazione 3D.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from core.line_mechanics import calculate_line_geometry
except ImportError:
    calculate_line_geometry = None

OFFSET_PLATFORM_FWD_M = 27.5
OFFSET_PLATFORM_AFT_M = 14.0


def calculate_bollard_coordinates(
    position_type, dist_inc, slope_deg, ship_loa, ship_beam
):
    """
    Calcola le coordinate X, Y, Z della bitta rispetto alle Observation Platforms.
    - Prua: X_platform + dist_horiz (+X)
    - Poppa: X_platform - dist_horiz (-X)
    """
    slope_rad = np.radians(slope_deg)
    dist_horiz = abs(dist_inc) * np.cos(slope_rad)
    z_m = -1.0 * (abs(dist_inc) * np.sin(slope_rad))

    if position_type == "Prua":
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
        x_m = x_platform + dist_horiz
    else:
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M
        x_m = x_platform - dist_horiz

    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def generate_detailed_3d_ship(ship_dict, offset_fugro: float = 0.0):
    """Genera lo scafo 3D traslato dell'offset FUGRO."""
    loa = ship_dict.get("LOA", 323.44)
    beam_hull = ship_dict.get("Beam", 37.20)
    beam_max = ship_dict.get("Beam_Max", 49.40)
    draft = ship_dict.get("Draft", 8.25)
    freeboard = ship_dict.get("Freeboard", 2.65)
    bridge_bow = ship_dict.get("Bridge_To_Bow", 39.50)
    bridge_eye_h = ship_dict.get("Bridge_Eye_Height", 26.40)

    loa_half = loa / 2.0
    beam_half = beam_hull / 2.0
    deck_z = freeboard
    bottom_z = -draft

    traces = []

    # Scafo 3D traslato in X dell'offset
    x_v = np.array([
        -loa_half, loa_half * 0.7, loa_half, loa_half * 0.7, -loa_half,
        -loa_half, loa_half * 0.7, loa_half, loa_half * 0.7, -loa_half
    ]) + offset_fugro

    y_v = [-beam_half, -beam_half, 0, beam_half, beam_half, -beam_half, -beam_half, 0, beam_half, beam_half]
    z_v = [deck_z] * 5 + [bottom_z] * 5

    i_faces = [0, 0, 0, 0, 5, 5, 0, 1, 1, 2, 2, 3, 3, 4]
    j_faces = [1, 2, 3, 4, 6, 7, 5, 6, 2, 7, 3, 8, 4, 9]
    k_faces = [2, 3, 4, 1, 7, 8, 1, 2, 7, 3, 8, 4, 9, 5]

    traces.append(
        go.Mesh3d(
            x=x_v, y=y_v, z=z_v,
            i=i_faces, j=j_faces, k=k_faces,
            color="navy", opacity=0.85, name="Scafo Solido 3D"
        )
    )

    # Sovrastruttura
    x_s = np.array([
        -loa_half * 0.85, loa_half * 0.65, loa_half * 0.65, -loa_half * 0.85,
        -loa_half * 0.85, loa_half * 0.65, loa_half * 0.65, -loa_half * 0.85
    ]) + offset_fugro
    y_s = [-beam_half * 0.9, -beam_half * 0.9, beam_half * 0.9, beam_half * 0.9, -beam_half * 0.9, -beam_half * 0.9, beam_half * 0.9, beam_half * 0.9]
    z_s = [deck_z] * 4 + [35.0] * 4

    traces.append(
        go.Mesh3d(
            x=x_s, y=y_s, z=z_s,
            i=[0, 0, 0, 1, 2, 3, 4, 4, 0, 1, 2, 3],
            j=[1, 2, 4, 5, 6, 7, 5, 6, 3, 2, 6, 7],
            k=[2, 3, 5, 6, 7, 4, 6, 7, 4, 5, 1, 0],
            color="royalblue", opacity=0.75, name="Sovrastruttura 3D"
        )
    )

    # Plancia
    bridge_x = (loa_half - bridge_bow) + offset_fugro
    wing_y = beam_max / 2.0
    traces.append(
        go.Scatter3d(
            x=[bridge_x, bridge_x], y=[-wing_y, wing_y], z=[bridge_eye_h, bridge_eye_h],
            mode="lines+markers", line=dict(color="red", width=8), name=f"Plancia ({beam_max}m)"
        )
    )

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina & Bitte Fisse — {selected_port}")
    
    offset_fugro = float(st.session_state.get("offset_fugro_m", 0.0))
    st.caption(
        f"🚢 **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** | "
        f"Offset da pos. FUGRO: **{offset_fugro:+.2f} m**"
    )

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    # Ricalcola le coordinate se le bitte non sono congelate
    for idx, row in df_bollards.iterrows():
        if not row.get("is_frozen", False):
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

    col_edit, col_map = st.columns([1.1, 1.1])

    with col_edit:
        st.subheader("📋 Gestione Dynamic Bitte Banchina")
        st.info(
            "📐 **Riferimenti Observation Platforms:**\n"
            "- **Prua:** Distanza sommata verso prua (`+X`)\n"
            "- **Poppa:** Distanza sottratta verso poppa (`-X`)\n\n"
            "Puoi aggiungere/rimuovere righe con i pulsanti `+` e `🗑️`."
        )

        edited_df = st.data_editor(
            df_bollards[[
                "bollard_id",
                "Posizione",
                "Dist_Inclinata_m",
                "Pendenza_deg",
                "SWL_Bitta_t",
                "Stato",
            ]],
            num_rows="dynamic",
            hide_index=True,
            use_container_width=True,
            column_config={
                "bollard_id": st.column_config.TextColumn("ID Bitta", required=True),
                "Posizione": st.column_config.SelectboxColumn("Posizione", options=["Prua", "Poppa"], default="Prua", required=True),
                "Dist_Inclinata_m": st.column_config.NumberColumn("Dist. Inclinata (m)", default=15.0, min_value=0.0, step=0.5),
                "Pendenza_deg": st.column_config.NumberColumn("Pendenza (°)", default=0.0, step=1.0),
                "SWL_Bitta_t": st.column_config.NumberColumn("SWL (t)", default=100.0, min_value=10.0),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["In Uso", "Disponibile", "Danneggiata"], default="Disponibile"),
            }
        )

        if st.button("💾 Salva / Congela Layout Banchina", type="primary"):
            updated_rows = []
            for idx, row in edited_df.iterrows():
                b_id = str(row.get("bollard_id", f"B{idx+1}")).strip()
                if not b_id:
                    b_id = f"B{idx+1}"
                
                pos = row.get("Posizione", "Prua")
                d_inc = float(row.get("Dist_Inclinata_m", 15.0) or 15.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                swl = float(row.get("SWL_Bitta_t", 100.0) or 100.0)
                stato = row.get("Stato", "Disponibile")

                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates(
                    pos, d_inc, p_deg, ship_dict["LOA"], ship_dict["Beam"]
                )

                updated_rows.append({
                    "bollard_id": b_id,
                    "Posizione": pos,
                    "Dist_Inclinata_m": d_inc,
                    "Pendenza_deg": p_deg,
                    "Dist_Orizzontale_m": d_horiz,
                    "X_Coordinata_m": x_calc,
                    "Y_Coordinata_m": y_calc,
                    "Z_Altezza_m": z_calc,
                    "bollard_x_m": x_calc,
                    "bollard_y_m": y_calc,
                    "bollard_z_m": z_calc,
                    "SWL_Bitta_t": swl,
                    "Stato": stato,
                    "is_frozen": True
                })

            final_df = pd.DataFrame(updated_rows)
            st.session_state.ports_bollards[selected_port] = final_df
            st.success(f"Layout salvato! Registrate {len(final_df)} bitte fisse a terra.")
            st.rerun()

    with col_map:
        st.subheader("🧊 Modellazione 3D Volumetric")
        fig = go.Figure()

        # 1. Nave Traslata
        ship_traces = generate_detailed_3d_ship(ship_dict, offset_fugro=offset_fugro)
        for trace in ship_traces:
            fig.add_trace(trace)

        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)
        berth_y = (beam / 2.0) + 6.4

        # 2. Banchina Fissa
        fig.add_trace(
            go.Mesh3d(
                x=[-loa * 0.65, loa * 0.65, loa * 0.65, -loa * 0.65, -loa * 0.65, loa * 0.65, loa * 0.65, -loa * 0.65],
                y=[berth_y, berth_y, berth_y + 15, berth_y + 15, berth_y, berth_y, berth_y + 15, berth_y + 15],
                z=[-6, -6, -6, -6, 0, 0, 0, 0],
                i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0],
                j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
                k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
                color="slategrey", opacity=0.5, name="Banchina"
            )
        )

        # 3. Bitte Fisse
        if not df_bollards.empty and "X_Coordinata_m" in df_bollards.columns:
            fig.add_trace(
                go.Scatter3d(
                    x=df_bollards["X_Coordinata_m"],
                    y=df_bollards["Y_Coordinata_m"],
                    z=df_bollards["Z_Altezza_m"],
                    mode="markers+text",
                    name="Bitte Banchina (Fisse)",
                    text=df_bollards["bollard_id"],
                    textposition="bottom center",
                    marker=dict(size=7, color="red", symbol="square"),
                )
            )

        # 4. Cavi Ricalcolati
        if calculate_line_geometry is not None and "lines_inventory" in st.session_state:
            try:
                geom_df = calculate_line_geometry(
                    st.session_state.lines_inventory,
                    df_bollards,
                    loa=loa,
                    offset_fugro=offset_fugro
                )
                if geom_df is not None and not geom_df.empty:
                    for _, line in geom_df.iterrows():
                        fig.add_trace(
                            go.Scatter3d(
                                x=[line["chock_x_m"], line["bollard_x_m"]],
                                y=[line["chock_y_m"], line["bollard_y_m"]],
                                z=[line["chock_z_m"], line["bollard_z_m"]],
                                mode="lines",
                                line=dict(color="orange", width=4),
                                name=f"Cavo {line.get('line_id', '')}",
                                showlegend=False,
                            )
                        )
            except Exception:
                pass

        fig.update_layout(
            scene=dict(
                xaxis=dict(title="X / Longitudinale (m)"),
                yaxis=dict(title="Y / Trasversale (m)"),
                zaxis=dict(title="Z / Verticale (m)"),
                aspectmode="data",
                camera=dict(center=dict(x=0, y=0, z=0), eye=dict(x=1.3, y=-1.3, z=0.9)),
            ),
            height=650, margin=dict(l=0, r=0, b=0, t=30),
        )
        st.plotly_chart(fig, use_container_width=True)
