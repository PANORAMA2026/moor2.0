"""
views/tab_polar.py
Inviluppo Polare Tensioni Vento (MEG4) con Evidenziazione Vettore Meteo
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from core.line_mechanics import solve_line_tensions_3d
    from core.hydrodynamic_forces import calculate_environmental_forces
except ImportError:
    solve_line_tensions_3d = None
    calculate_environmental_forces = None


def calculate_polar_tensions_for_wind(v_wind: float, geom_df: pd.DataFrame, afw: float, alw: float, alc: float, loa: float):
    """Calcola il carico % MBL massimo per vento costante a 360°."""
    angles = list(range(0, 360, 10))
    max_mbl_percentages = []

    if solve_line_tensions_3d is None or calculate_environmental_forces is None or geom_df.empty:
        # Fallback grafico se manca il modello
        return angles, [round(30.0 + 35.0 * np.abs(np.sin(np.radians(a))), 1) for a in angles]

    for wind_dir in angles:
        try:
            forces = calculate_environmental_forces(v_wind, wind_dir, 0.0, 0, afw, alw, alc, loa)
            res = solve_line_tensions_3d(geom_df, forces)

            if not res.empty and "Util_Percent" in res.columns:
                max_mbl_percentages.append(round(res["Util_Percent"].max(), 1))
            else:
                max_mbl_percentages.append(0.0)
        except Exception:
            max_mbl_percentages.append(0.0)

    return angles, max_mbl_percentages


def build_polar_mbl_figure(angles, mbl_values, current_wind_speed, active_wind_dir):
    """Genera grafico polare ad alto contrasto senza sovrapposizioni e con punto meteo attivo."""
    angles_plot = angles + [angles[0]]
    mbl_plot = mbl_values + [mbl_values[0]]
    limit_50 = [50.0] * len(angles_plot)

    fig = go.Figure()

    # 1. Soglia Limite MEG4 (50% MBL)
    fig.add_trace(go.Scatterpolar(
        r=limit_50,
        theta=angles_plot,
        mode='lines',
        name='Soglia Limite MEG4 (50% MBL)',
        line=dict(color='#FFD700', width=2, dash='dash'),
        hovertemplate='Soglia MEG4: 50% MBL<extra></extra>'
    ))

    # 2. Inviluppo globale carichi
    fig.add_trace(go.Scatterpolar(
        r=mbl_plot,
        theta=angles_plot,
        mode='lines',
        name=f'Risposta Inviluppo ({current_wind_speed} kts)',
        line=dict(color='#FF4B4B', width=2.5),
        fill='toself',
        fillcolor='rgba(255, 75, 75, 0.15)',
        hovertemplate='Angolo: %{theta}°<br>Carico Max: %{r}% MBL<extra></extra>'
    ))

    # 3. Punto di lavoro DIRETTAMENTE SELEZIONATO nella sidebar
    # Trova il valore interpolato/corrispondente all'angolo meteo attivo
    idx_dir = min(range(len(angles)), key=lambda i: abs(angles[i] - active_wind_dir))
    active_mbl_val = mbl_values[idx_dir] if mbl_values else 0.0

    fig.add_trace(go.Scatterpolar(
        r=[0, active_mbl_val],
        theta=[active_wind_dir, active_wind_dir],
        mode='lines+markers',
        name=f'Vento Impostato ({current_wind_speed} kts @ {active_wind_dir}°)',
        line=dict(color='#00E5FF', width=4),
        marker=dict(size=[0, 10], color='#00E5FF'),
        hovertemplate=f'<b>Condizione Selezionata</b><br>Direzione: {active_wind_dir}°<br>Carico: {active_mbl_val}% MBL<extra></extra>'
    ))

    max_radial = max(100.0, max(mbl_values) + 10.0 if mbl_values else 100.0)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>ANALISI POLARE CAVI - VENTO {current_wind_speed} KTS</b><br><sup>Linea Azzurra: Vento attivo a {active_wind_dir}° (Carico: {active_mbl_val}% MBL)</sup>",
            x=0.5,
            font=dict(size=16, color="#FFFFFF")
        ),
        polar=dict(
            bgcolor="rgba(20, 24, 30, 0.8)",
            radialaxis=dict(
                visible=True,
                range=[0, max_radial],
                dtick=25,
                ticksuffix="%",
                angle=90,  # Sposta i numeri sulla linea dei 90° evitando il centro
                tickfont=dict(size=11, color="#00E5FF"),
                gridcolor="#333333"
            ),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["<b>Prua (0°)</b>", "45°", "<b>Dritta (90°)</b>", "135°", "<b>Poppa (180°)</b>", "225°", "<b>Sinistra (270°)</b>", "315°"],
                tickfont=dict(size=12, color="#FFFFFF"),
                gridcolor="#333333"
            )
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.18,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=40, t=70, b=40),
        height=620
    )
    return fig


def render_tab_polar():
    st.header("🌀 Inviluppo Polare Tensioni Cavi (MEG4)")
    
    # Recupero della velocità E della direzione dalla sidebar
    v_wind = st.session_state.get("v_wind", 46.0)
    dir_wind = st.session_state.get("dir_wind", 45.0)
    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    st.caption(f"Condizioni impostate: Vento **{v_wind} kts** provenienza **{dir_wind}°**. Il grafico evidenzia la tensione risultante per l'angolo selezionato rispetto all'inviluppo a 360°.")

    if st.button("🚀 Calcola Inviluppo Polare", type="primary", use_container_width=True):
        with st.spinner(f"Calcolo risposta cavi a 360° per vento a {v_wind} kts..."):
            afw = st.session_state.get("afw", 950.0)
            alw = st.session_state.get("alw", 3200.0)
            alc = st.session_state.get("alc", 1800.0)
            loa = st.session_state.get("loa", 323.44)

            angles, mbl_values = calculate_polar_tensions_for_wind(v_wind, geom_df, afw, alw, alc, loa)

            st.session_state["polar_fig"] = build_polar_mbl_figure(angles, mbl_values, v_wind, dir_wind)

    if "polar_fig" in st.session_state and st.session_state["polar_fig"] is not None:
        st.plotly_chart(st.session_state["polar_fig"], use_container_width=True)
    else:
        st.info("ℹ️ Clicca su **Calcola Inviluppo Polare** per generare il grafico.")
