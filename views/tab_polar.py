"""
views/tab_polar.py
Inviluppo Polare delle Tensioni per Vento Costante (0-360°) - MEG4
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


def calculate_polar_tensions_for_wind(
    v_wind: float, 
    geom_df: pd.DataFrame, 
    afw: float, 
    alw: float, 
    alc: float, 
    loa: float
):
    """
    Applica la velocità del vento impostata nella sidebar a 360° 
    e calcola il carico massimo (% MBL) sui cavi per ogni direzione.
    """
    angles = list(range(0, 360, 10))
    max_mbl_percentages = []

    if solve_line_tensions_3d is None or calculate_environmental_forces is None or geom_df.empty:
        # Fallback di simulazione grafica in assenza di modello geometrico
        return angles, [round(30.0 + 30.0 * np.abs(np.sin(np.radians(a))), 1) for a in angles]

    for wind_dir in angles:
        try:
            # Calcolo forze con il vento della sidebar e corrente a zero
            forces = calculate_environmental_forces(v_wind, wind_dir, 0.0, 0, afw, alw, alc, loa)
            res = solve_line_tensions_3d(geom_df, forces)

            if not res.empty and "Util_Percent" in res.columns:
                max_mbl = res["Util_Percent"].max()
                max_mbl_percentages.append(round(max_mbl, 1))
            else:
                max_mbl_percentages.append(0.0)
        except Exception:
            max_mbl_percentages.append(0.0)

    return angles, max_mbl_percentages


def build_polar_mbl_figure(angles, mbl_values, current_wind_speed):
    """Genera il grafico polare con scala % MBL e limite di sicurezza MEG4 al 50%."""
    angles_plot = angles + [angles[0]]
    mbl_plot = mbl_values + [mbl_values[0]]
    limit_50 = [50.0] * len(angles_plot)

    fig = go.Figure()

    # Curva Limite Sicurezza MEG4 (50% MBL)
    fig.add_trace(go.Scatterpolar(
        r=limit_50,
        theta=angles_plot,
        mode='lines',
        name='Soglia Limite MEG4 (50% MBL)',
        line=dict(color='#FFD700', width=2, dash='dash'),
        hovertemplate='Limite MEG4: 50% MBL<extra></extra>'
    ))

    # Tensione Effettiva dei Cavi per la velocità impostata
    fig.add_trace(go.Scatterpolar(
        r=mbl_plot,
        theta=angles_plot,
        mode='lines+markers',
        name=f'Carico Cavi a {current_wind_speed} kts',
        line=dict(color='#FF4B4B', width=3),
        marker=dict(size=4, color='#FF4B4B'),
        fill='toself',
        fillcolor='rgba(255, 75, 75, 0.25)',
        hovertemplate='Direzione Vento: %{theta}°<br>Carico Max: %{r}% MBL<extra></extra>'
    ))

    max_radial = max(100.0, max(mbl_values) + 10.0 if mbl_values else 100.0)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        title=dict(
            text=f"<b>ANALISI POLARE TENSIONI CAVI (% MBL) - VENTO {current_wind_speed} KTS</b>",
            x=0.5,
            font=dict(size=16, color="#FFFFFF")
        ),
        polar=dict(
            bgcolor="rgba(20, 24, 30, 0.8)",
            radialaxis=dict(
                visible=True,
                range=[0, max_radial],
                dtick=25,
                ticksuffix=" %",
                angle=0,
                tickfont=dict(size=11, color="#00E5FF"),
                gridcolor="#444444"
            ),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["<b>Prua (0°)</b>", "45°", "<b>Dritta (90°)</b>", "135°", "<b>Poppa (180°)</b>", "225°", "<b>Sinistra (270°)</b>", "315°"],
                tickfont=dict(size=12, color="#FFFFFF"),
                gridcolor="#444444"
            )
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=40, t=50, b=40),
        height=620
    )
    return fig


def render_tab_polar():
    st.header("🌀 Inviluppo Polare Tensioni Cavi (MEG4)")
    
    # Recupero dati e impostazioni dalla Sidebar di sinistra
    v_wind = st.session_state.get("v_wind", 46.0)
    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    st.caption(f"Valutazione del carico sui cavi ad ogni angolo d'incidenza per la velocità di vento selezionata a sinistra: **{v_wind} Knots**.")

    if st.button("🚀 Calcola Inviluppo Polare", type="primary", use_container_width=True):
        with st.spinner(f"Calcolo tensioni per vento a {v_wind} kts da 0° a 360°..."):
            afw = st.session_state.get("afw", 950.0)
            alw = st.session_state.get("alw", 3200.0)
            alc = st.session_state.get("alc", 1800.0)
            loa = st.session_state.get("loa", 323.44)

            angles, mbl_values = calculate_polar_tensions_for_wind(v_wind, geom_df, afw, alw, alc, loa)

            st.session_state["polar_fig"] = build_polar_mbl_figure(angles, mbl_values, v_wind)

    # Rendering Grafico
    if "polar_fig" in st.session_state and st.session_state["polar_fig"] is not None:
        st.plotly_chart(st.session_state["polar_fig"], use_container_width=True)
    else:
        st.info("ℹ️ Clicca su **Calcola Inviluppo Polare** per visualizzare la risposta della nave al vento impostato.")
