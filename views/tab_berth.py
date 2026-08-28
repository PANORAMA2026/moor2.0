"""
views/tab_berth.py
Gestione layout banchina separata in due stazioni (Prua e Poppa).
Calcolo coordinate, calcolo rigidezza con 10% pretensione e passaggio dati allo State.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from core.line_mechanics import calculate_line_geometry, solve_line_tensions_3d
except ImportError:
    calculate_line_geometry = None
    solve_line_tensions_3d = None

from database.db_manager import save_port_bollards_to_db, load_port_bollards_from_db

OFFSET_PLATFORM_FWD_M = 25.0
OFFSET_PLATFORM_AFT_M = 14.0


def calculate_bollard_coordinates(position_type: str, dist_signed: float, slope_deg: float, ship_loa: float, ship_beam: float):
    slope_rad = np.radians(slope_deg)
    dist_horiz = dist_signed * np.cos(slope_rad)
    z_m = -1.0 * (abs(dist_signed) * np.sin(slope_rad))

    if position_type == "Prua":
        x_platform = (ship_loa / 2.0) - OFFSET_PLATFORM_FWD_M
    else:
        x_platform = (-ship_loa / 2.0) + OFFSET_PLATFORM_AFT_M

    x_m = x_platform + dist_horiz
    y_m = (ship_beam / 2.0) + 6.4

    return round(dist_horiz, 2), round(x_m, 2), round(y_m, 2), round(z_m, 2)


def generate_detailed_3d_ship(ship_dict, offset_fugro: float = 0.0):
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
    x_v = np.array([
        -loa_half, loa_half * 0.7, loa_half, loa_half * 0.7, -loa_half,
        -loa_half, loa_half * 0.7, loa_half, loa_half * 0.7, -loa_half
    ]) + offset_fugro

    y_v = [-beam_half, -beam_half, 0, beam_half, beam_half, -beam_half, -beam_half, 0, beam_half, beam_half]
    z_v = [deck_z] * 5 + [bottom_z] * 5

    i_faces = [0, 0, 0, 0, 5, 5, 0, 1, 1, 2, 2, 3, 3, 4]
    j_faces = [1, 2, 3, 4, 6, 7, 5, 6, 2, 7, 3, 8, 4, 9]
    k_faces = [2, 3, 4, 1, 7, 8, 1, 2, 7, 3, 8, 4, 9, 5]

    traces.append(go.Mesh3d(x=x_v, y=y_v, z=z_v, i=i_faces, j=j_faces, k=k_faces, color="navy", opacity=0.85, name="Scafo Solido 3D"))

    x_s = np.array([
        -loa_half * 0.85, loa_half * 0.65, loa_half * 0.65, -loa_half * 0.85,
        -loa_half * 0.85, loa_half * 0.65, loa_half * 0.65, -loa_half * 0.85
    ]) + offset_fugro
    y_s = [-beam_half * 0.9, -beam_half * 0.9, beam_half * 0.9, beam_half * 0.9, -beam_half * 0.9, -beam_half * 0.9, beam_half * 0.9, beam_half * 0.9]
    z_s = [deck_z] * 4 + [35.0] * 4

    traces.append(go.Mesh3d(x=x_s, y=y_s, z=z_s, i=[0, 0, 0, 1, 2, 3, 4, 4, 0, 1, 2, 3], j=[1, 2, 4, 5, 6, 7, 5, 6, 3, 2, 6, 7], k=[2, 3, 5, 6, 7, 4, 6, 7, 4, 5, 1, 0], color="royalblue", opacity=0.75, name="Sovrastruttura 3D"))

    bridge_x = (loa_half - bridge_bow) + offset_fugro
    wing_y = beam_max / 2.0
    traces.append(go.Scatter3d(x=[bridge_x, bridge_x], y=[-wing_y, wing_y], z=[bridge_eye_h, bridge_eye_h], mode="lines+markers", line=dict(color="red", width=8), name=f"Plancia ({beam_max}m)"))

    return traces


def render_tab_berth(selected_port, ship_dict):
    st.header(f"🗺️ Layout Banchina — {selected_port}")
    
    offset_fugro = float(st.session_state.get("offset_fugro_m", 0.0))
    st.caption(f"🚢 **{ship_dict.get('Name')}** | LOA: **{ship_dict.get('LOA')}m** | Offset FUGRO: **{offset_fugro:+.2f} m**")

    # Caricamento dal DB se non presente nello state
    if "ports_bollards" not in st.session_state:
        st.session_state.ports_bollards = {}

    if selected_port not in st.session_state.ports_bollards:
        st.session_state.ports_bollards[selected_port] = load_port_bollards_from_db(selected_port)

    df_bollards = st.session_state.ports_bollards[selected_port].copy()

    col_edit, col_map = st.columns([1.1, 1.1])

    with col_edit:
        st.info("📐 **Convenzione Segni:** Positivo (`> 0`) verso **Prua** | Negativo (`< 0`) verso **Poppa**.")

        st.subheader("⚓ Stazione di Prua (Fwd Observation Platform)")
        df_prua = df_bollards[df_bollards["Posizione"] == "Prua"].copy() if not df_bollards.empty else pd.DataFrame()
        edited_prua = st.data_editor(
            df_prua[["bollard_id", "Dist_Inclinata_m", "Pendenza_deg", "SWL_Bitta_t", "Stato"]],
            num_rows="dynamic", hide_index=True, use_container_width=True, key="editor_prua",
            column_config={
                "bollard_id": st.column_config.TextColumn("ID Bitta", required=True),
                "Dist_Inclinata_m": st.column_config.NumberColumn("Dist. da Fwd Obs. (+Prua / -Poppa)", default=0.0, step=0.5),
                "Pendenza_deg": st.column_config.NumberColumn("Pendenza (°)", default=0.0, step=1.0),
                "SWL_Bitta_t": st.column_config.NumberColumn("SWL (t)", default=100.0, min_value=10.0),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["In Uso", "Disponibile", "Danneggiata"], default="Disponibile"),
            }
        )

        st.divider()

        st.subheader("⚓ Stazione di Poppa (Aft Observation Platform)")
        df_poppa = df_bollards[df_bollards["Posizione"] == "Poppa"].copy() if not df_bollards.empty else pd.DataFrame()
        edited_poppa = st.data_editor(
            df_poppa[["bollard_id", "Dist_Inclinata_m", "Pendenza_deg", "SWL_Bitta_t", "Stato"]],
            num_rows="dynamic", hide_index=True, use_container_width=True, key="editor_poppa",
            column_config={
                "bollard_id": st.column_config.TextColumn("ID Bitta", required=True),
                "Dist_Inclinata_m": st.column_config.NumberColumn("Dist. da Aft Obs. (+Prua / -Poppa)", default=0.0, step=0.5),
                "Pendenza_deg": st.column_config.NumberColumn("Pendenza (°)", default=0.0, step=1.0),
                "SWL_Bitta_t": st.column_config.NumberColumn("SWL (t)", default=100.0, min_value=10.0),
                "Stato": st.column_config.SelectboxColumn("Stato", options=["In Uso", "Disponibile", "Danneggiata"], default="Disponibile"),
            }
        )

        if st.button("💾 Salva Layout Permanentemente su DB", type="primary"):
            updated_rows = []

            for idx, row in edited_prua.iterrows():
                b_id = str(row.get("bollard_id", f"BP{idx+1}")).strip() or f"BP{idx+1}"
                d_signed = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates("Prua", d_signed, p_deg, ship_dict["LOA"], ship_dict["Beam"])
                updated_rows.append({
                    "bollard_id": b_id, "Posizione": "Prua", "Dist_Inclinata_m": d_signed, "Pendenza_deg": p_deg,
                    "Dist_Orizzontale_m": d_horiz, "X_Coordinata_m": x_calc, "Y_Coordinata_m": y_calc, "Z_Altezza_m": z_calc,
                    "bollard_x_m": x_calc, "bollard_y_m": y_calc, "bollard_z_m": z_calc,
                    "SWL_Bitta_t": float(row.get("SWL_Bitta_t", 100.0) or 100.0), "Stato": row.get("Stato", "Disponibile"), "is_frozen": True
                })

            for idx, row in edited_poppa.iterrows():
                b_id = str(row.get("bollard_id", f"BA{idx+1}")).strip() or f"BA{idx+1}"
                d_signed = float(row.get("Dist_Inclinata_m", 0.0) or 0.0)
                p_deg = float(row.get("Pendenza_deg", 0.0) or 0.0)
                d_horiz, x_calc, y_calc, z_calc = calculate_bollard_coordinates("Poppa", d_signed, p_deg, ship_dict["LOA"], ship_dict["Beam"])
                updated_rows.append({
                    "bollard_id": b_id, "Posizione": "Poppa", "Dist_Inclinata_m": d_signed, "Pendenza_deg": p_deg,
                    "Dist_Orizzontale_m": d_horiz, "X_Coordinata_m": x_calc, "Y_Coordinata_m": y_calc, "Z_Altezza_m": z_calc,
                    "bollard_x_m": x_calc, "bollard_y_m": y_calc, "bollard_z_m": z_calc,
                    "SWL_Bitta_t": float(row.get("SWL_Bitta_t", 100.0) or 100.0), "Stato": row.get("Stato", "Disponibile"), "is_frozen": True
                })

            final_df = pd.DataFrame(updated_rows)
            st.session_state.ports_bollards[selected_port] = final_df
            
            save_port_bollards_to_db(selected_port, final_df)
            st.success(f"Layout salvato nel database fisso per {selected_port}!")
            st.rerun()

    with col_map:
        st.subheader("🧊 Modellazione 3D Volumetric")
        fig = go.Figure()
        for trace in generate_detailed_3d_ship(ship_dict, offset_fugro=offset_fugro):
            fig.add_trace(trace)

        loa = ship_dict.get("LOA", 323.44)
        beam = ship_dict.get("Beam", 37.20)
        berth_y = (beam / 2.0) + 6.4

        fig.add_trace(go.Mesh3d(
            x=[-loa * 0.65, loa * 0.65, loa * 0.65, -loa * 0.65, -loa * 0.65, loa * 0.65, loa * 0.65, -loa * 0.65],
            y=[berth_y, berth_y, berth_y + 15, berth_y + 15, berth_y, berth_y, berth_y + 15, berth_y + 15],
            z=[-6, -6, -6, -6, 0, 0, 0, 0], i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 0, 0], j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 3, 4],
            k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7], color="slategrey", opacity=0.5, name="Banchina"
        ))

        if not df_bollards.empty and "X_Coordinata_m" in df_bollards.columns:
            fig.add_trace(go.Scatter3d(
                x=df_bollards["X_Coordinata_m"], y=df_bollards["Y_Coordinata_m"], z=df_bollards["Z_Altezza_m"],
                mode="markers+text", name="Bitte Banchina", text=df_bollards["bollard_id"],
                textposition="bottom center", marker=dict(size=7, color="red", symbol="square")
            ))

        # CALCOLO GEOMETRIA & PRETENSIONAMENTO PER IL SALVATAGGIO IN STATE
        if calculate_line_geometry is not None and "lines_inventory" in st.session_state:
            try:
                lines_inv = st.session_state.lines_inventory
                geom_df = calculate_line_geometry(lines_inv, df_bollards, loa=loa, offset_fugro=offset_fugro)
                
                if geom_df is not None and not geom_df.empty:
                    # Risoluzione con pretensionamento iniziale al 10% (0 forze esterne di default)
                    if solve_line_tensions_3d is not None:
                        sim_df = solve_line_tensions_3d(geom_df, {"Fx_total_t": 0.0, "Fy_total_t": 0.0, "Mz_total_tm": 0.0}, pretension_pct=10.0)
                        st.session_state["latest_mooring_results"] = sim_df
                    
                    # Tracciamento cavi 3D
                    for _, line in geom_df.iterrows():
                        fig.add_trace(go.Scatter3d(
                            x=[line["chock_x_m"], line["bollard_x_m"]], 
                            y=[line["chock_y_m"], line["bollard_y_m"]], 
                            z=[line["chock_z_m"], line["bollard_z_m"]],
                            mode="lines", 
                            line=dict(color="orange", width=4), 
                            showlegend=False
                        ))
            except Exception as e:
                st.warning(f"Errore nel calcolo delle linee 3D: {e}")

        fig.update_layout(
            scene=dict(xaxis=dict(title="X (m)"), yaxis=dict(title="Y (m)"), zaxis=dict(title="Z (m)"), aspectmode="data"), 
            height=650, 
            margin=dict(l=0, r=0, b=0, t=30)
        )
        st.plotly_chart(fig, use_container_width=True)
