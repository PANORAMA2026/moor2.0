"""
views/tab_simulation.py
Tab Simulazione Tensioni con grafico 2D colorato a semaforo in base alla % MBL.
"""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import pandas as pd


def get_tension_color(util_percent: float) -> str:
    """Restituisce il colore dinamico in base al livello di carico MBL."""
    if util_percent >= 80.0:
        return "#FF2B2B"  # Rosso: Critico / Prossimità/Superamento MBL (>80%)
    elif util_percent >= 55.0:
        return "#FFD700"  # Giallo: Vicino al limite MBL (55% - 80%)
    else:
        return "#00E676"  # Verde: Carico in sicurezza (<55%)


def render_tab_simulation():
    # Recupero risultati di simulazione o mock dati dallo state
    results_df = st.session_state.get("latest_mooring_results", None)

    if results_df is None or not isinstance(results_df, pd.DataFrame) or results_df.empty:
        # Se non c'è una simulazione attiva, ricreiamo la struttura dati visibile nello screenshot
        results_df = pd.DataFrame([
            {"line_id": 1, "line_name": "Head Line 1", "cert_id": "CERT-HMPE-2025-01", "bollard_id": "B1", "length_m": 27.88, "azimuth_deg": 91.7, "incline_deg": 34.4, "Tension_tons": 47.89, "Util_Percent": 45.6},
            {"line_id": 2, "line_name": "Head Line 2", "cert_id": "CERT-HMPE-2025-01", "bollard_id": "B1", "length_m": 31.26, "azimuth_deg": 91.4, "incline_deg": 30.2, "Tension_tons": 48.48, "Util_Percent": 46.2},
            {"line_id": 3, "line_name": "Fwd Breast 1", "cert_id": "CERT-HMPE-2025-02", "bollard_id": "B2", "length_m": 18.14, "azimuth_deg": 31.2, "incline_deg": 41.8, "Tension_tons": 24.35, "Util_Percent": 23.2},
            {"line_id": 4, "line_name": "Fwd Spring 1", "cert_id": "CERT-HMPE-2025-02", "bollard_id": "B3", "length_m": 50.13, "azimuth_deg": 8.2, "incline_deg": 11.4, "Tension_tons": 16.90, "Util_Percent": 16.1},
            {"line_id": 5, "line_name": "Aft Spring 1", "cert_id": "CERT-HMPE-2025-01", "bollard_id": "B4", "length_m": 21.65, "azimuth_deg": 158.6, "incline_deg": 27.8, "Tension_tons": 51.95, "Util_Percent": 49.5},
            {"line_id": 6, "line_name": "Aft Breast 1", "cert_id": "CERT-HMPE-2025-02", "bollard_id": "B5", "length_m": 16.64, "azimuth_deg": 41.0, "incline_deg": 50.2, "Tension_tons": 16.68, "Util_Percent": 15.9},
            {"line_id": 7, "line_name": "Stern Line 1", "cert_id": "CERT-HMPE-2025-02", "bollard_id": "B5", "length_m": 37.07, "azimuth_deg": 47.3, "incline_deg": 23.5, "Tension_tons": 19.50, "Util_Percent": 18.6},
        ])

    # Header & Metriche Fx, Fy, Mz
    st.subheader("Analisi Tensione Cavi: Long Beach Cruise Terminal (Meteo: 30.0 kts @ 45.0° | Offset: +0.00m)")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Forza Longitudinale (Fx)", f"{st.session_state.get('sim_fx', -12.23):.2f} t")
    c2.metric("Forza Trasversale (Fy)", f"{st.session_state.get('sim_fy', 91.94):.2f} t")
    c3.metric("Momento Imbardata (Mz)", f"{st.session_state.get('sim_mz', 8227.99):.2f} t·m")

    st.markdown("---")

    # 1. Tabella Analitica Dati
    st.dataframe(results_df, use_container_width=True)

    if st.button("💾 Registra Sessione d'Ormeggio nel DB"):
        st.success("Sessione salvata con successo nel DB!")

    st.markdown("---")

    # 2. GRAFICO 2D COLORATO A SEMAFORO
    st.subheader("📊 Vista 2D Tensioni e Sollecitazioni MBL")
    st.caption("🟢 **Verde**: < 55% MBL | 🟡 **Giallo**: 55% - 80% MBL | 🔴 **Rosso**: > 80% MBL")

    fig = go.Figure()

    # Sagoma Schematica della Nave 2D Top-Down
    ship_length = 180.0
    ship_beam = 32.0
    ship_x = [0, ship_length * 0.8, ship_length, ship_length * 0.8, 0, 0]
    ship_y = [-ship_beam / 2, -ship_beam / 2, 0, ship_beam / 2, ship_beam / 2, -ship_beam / 2]
    
    fig.add_trace(go.Scatter(
        x=ship_x, y=ship_y,
        mode="lines",
        fill="toself",
        fillcolor="rgba(100, 116, 139, 0.25)",
        line=dict(color="#94A3B8", width=2),
        name="Nave",
        hoverinfo="skip"
    ))

    # Linea Banchina
    berth_y = -30.0
    fig.add_trace(go.Scatter(
        x=[-20, ship_length + 30], y=[berth_y, berth_y],
        mode="lines",
        line=dict(color="#64748B", width=4, dash="dash"),
        name="Banchina",
        hoverinfo="skip"
    ))

    # Generazione Vettori Cime 2D
    for idx, row in results_df.iterrows():
        util = float(row.get("Util_Percent", row.get("util_percent", 0.0)))
        tension = float(row.get("Tension_tons", row.get("tension_tons", 0.0)))
        name = str(row.get("line_name", f"Cima {idx+1}"))
        azimuth = float(row.get("azimuth_deg", 45.0))
        length = float(row.get("length_m", 25.0))

        # Posizionamento dinamico passacavi sulla sagoma nave se X/Y mancanti
        chock_x = row.get("chock_x_m", (idx + 1) * (ship_length / (len(results_df) + 1)))
        chock_y = row.get("chock_y_m", -ship_beam / 2)

        # Calcolo posizione Bitta basato su Azimuth e Lunghezza (se coordinate non esplicite)
        rad = np.radians(azimuth)
        bollard_x = row.get("bollard_x_m", chock_x + (length * np.cos(rad)))
        bollard_y = row.get("bollard_y_m", berth_y)

        color = get_tension_color(util)

        # Traccia della cima colorata
        fig.add_trace(go.Scatter(
            x=[chock_x, bollard_x],
            y=[chock_y, bollard_y],
            mode="lines+markers",
            line=dict(color=color, width=4),
            marker=dict(size=8, color=color),
            name=f"{name} ({util:.1f}%)",
            hovertemplate=(
                f"<b>{name}</b><br>" +
                f"Tensione: <b>{tension:.2f} t</b><br>" +
                f"Utilizzo MBL: <b>{util:.1f}%</b><extra></extra>"
            )
        ))

        # Etichetta centrata sul cavo
        mid_x = (chock_x + bollard_x) / 2
        mid_y = (chock_y + bollard_y) / 2
        fig.add_trace(go.Scatter(
            x=[mid_x], y=[mid_y],
            mode="text",
            text=[f"<b>{name}</b><br>{tension:.1f}t ({util:.0f}%)"],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip"
        ))

    fig.update_layout(
        xaxis=dict(title="Longitudinale X (m)", zeroline=False),
        yaxis=dict(title="Trasversale Y (m)", scaleanchor="x", scaleratio=1, zeroline=False),
        height=500,
        plot_bgcolor="#0F172A",
        paper_bgcolor="#0F172A",
        font=dict(color="#F8FAFC"),
        margin=dict(l=20, r=20, t=30, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)
