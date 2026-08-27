"""
views/tab_simulation.py
Tab Simulazione Tensioni: Mantiene la tabella analitica originale e integra
il grafico 2D Top-Down con codifica colori MBL (Verde/Giallo/Rosso).
"""

import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from database.db_manager import (
    load_lines_inventory_from_db,
    log_mooring_session
)


def get_tension_color(util_percent: float) -> str:
    """Restituisce il colore dinamico in base alla % di MBL utilizzata."""
    if util_percent >= 80.0:
        return "#FF2B2B"  # Rosso: Critico / Oltre 80% MBL
    elif util_percent >= 55.0:
        return "#FFD700"  # Giallo: Prossimità al limite (55% - 80% MBL)
    else:
        return "#00E676"  # Verde: Sicuro (< 55% MBL)


def render_tab_simulation():
    # Recupero dati calcolati o dall'inventario
    lines_df = load_lines_inventory_from_db()
    results_df = st.session_state.get("latest_mooring_results", None)

    if results_df is None:
        results_df = lines_df.copy()
        if "tension_tons" not in results_df.columns:
            results_df["tension_tons"] = 0.0
        if "util_percent" not in results_df.columns:
            results_df["util_percent"] = (results_df["tension_tons"] / results_df.get("mbl_tons", 1.0)) * 100

    # 1. Indicatori Sintetici (Fx, Fy, Mz)
    st.subheader(f"Analisi Tensione Cavi: {st.session_state.get('current_port', 'Long Beach Cruise Terminal')}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Forza Longitudinale (Fx)", f"{st.session_state.get('sim_fx', -12.23):.2f} t")
    c2.metric("Forza Trasversale (Fy)", f"{st.session_state.get('sim_fy', 91.94):.2f} t")
    c3.metric("Momento Imbardata (Mz)", f"{st.session_state.get('sim_mz', 8227.99):.2f} t·m")

    st.markdown("---")

    # 2. TABELLA ORIGINALE (Preservata esattamente come nello screenshot)
    st.dataframe(
        results_df,
        use_container_width=True,
        hide_index=False
    )

    if st.button("💾 Registra Sessione d'Ormeggio nel DB"):
        port_name = st.session_state.get("current_port", "Porto Principale")
        log_mooring_session(results_df, port_name)
        st.success("Sessione registrata con successo nel database!")

    st.markdown("---")

    # 3. NUOVO GRAFICO 2D AGGIUNTIVO (Codificato a colori in base all'MBL)
    st.subheader("📊 Mappa 2D Focus Tensioni & Limiti MBL")
    st.caption("🟢 Verde: < 55% MBL | 🟡 Giallo: 55% - 80% MBL | 🔴 Rosso: > 80% MBL")

    fig = go.Figure()

    # Sagoma Schematica Nave (Vista dall'alto)
    ship_x = [-10, 150, 170, 150, -10, -10]
    ship_y = [-15, -15, 0, 15, 15, -15]
    fig.add_trace(go.Scatter(
        x=ship_x, y=ship_y,
        mode="lines",
        fill="toself",
        fillcolor="rgba(200, 210, 225, 0.25)",
        line=dict(color="#4A5568", width=2),
        name="Nave",
        hoverinfo="skip"
    ))

    # Linea Banchina
    fig.add_trace(go.Scatter(
        x=[-30, 190], y=[-30, -30],
        mode="lines",
        line=dict(color="#718096", width=4, dash="dash"),
        name="Banchina",
        hoverinfo="skip"
    ))

    # Rendering delle cime con colore dinamico
    for idx, line in results_df.iterrows():
        chock_x = float(line.get("chock_x_m", idx * 20.0))
        chock_y = float(line.get("chock_y_m", 15.0 if idx % 2 == 0 else -15.0))
        bollard_x = float(line.get("bollard_x_m", chock_x + 5.0))
        bollard_y = float(line.get("bollard_y_m", -30.0))

        tension = float(line.get("Tension_tons", line.get("tension_tons", 0.0)))
        util = float(line.get("Util_Percent", line.get("util_percent", 0.0)))
        line_name = str(line.get("line_name", line.get("line_id", f"Line {idx+1}")))

        color = get_tension_color(util)

        # Traccia Cima
        fig.add_trace(go.Scatter(
            x=[chock_x, bollard_x],
            y=[chock_y, bollard_y],
            mode="lines+markers",
            line=dict(color=color, width=4),
            marker=dict(size=8, color=color),
            name=f"{line_name} ({util:.1f}%)",
            hovertemplate=(
                f"<b>{line_name}</b><br>" +
                f"Tensione: <b>{tension:.2f} t</b><br>" +
                f"Utilizzo MBL: <b>{util:.1f}%</b><extra></extra>"
            )
        ))

        # Etichetta di testo a metà cavo
        mid_x = (chock_x + bollard_x) / 2
        mid_y = (chock_y + bollard_y) / 2
        fig.add_trace(go.Scatter(
            x=[mid_x], y=[mid_y],
            mode="text",
            text=[f"<b>{line_name}</b><br>{tension:.1f}t ({util:.0f}%)"],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip"
        ))

    fig.update_layout(
        xaxis=dict(title="Posizione Longitudinale X (m)", zeroline=False),
        yaxis=dict(title="Posizione Trasversale Y (m)", scaleanchor="x", scaleratio=1, zeroline=False),
        height=550,
        plot_bgcolor="#1A202C",
        paper_bgcolor="#1A202C",
        font=dict(color="#E2E8F0"),
        margin=dict(l=20, r=20, t=30, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)
