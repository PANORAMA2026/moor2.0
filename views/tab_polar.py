"""
views/tab_polar.py
Inviluppo Polare di Operabilità Vento stile OPTIMOOR (MEG4).
Mostra in modo dinamico solo le curve per cui sono presenti i dati (Line, Bollard, Fender).
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from core.line_mechanics import solve_line_tensions_3d
from core.hydrodynamic_forces import calculate_environmental_forces


def calculate_multi_limit_polar_envelope(
    geom_df: pd.DataFrame, 
    afw: float, 
    alw: float, 
    alc: float, 
    loa: float, 
    v_curr: float, 
    dir_curr: float, 
    mbl_limit_pct: float = 50.0
):
    """
    Calcola dinamicamente le curve di inviluppo in base ai dati disponibili:
    1. Line Limit (Sempre calcolato - es. 50% MBL)
    2. Bollard Limit (Calcolato solo se bollard_swl è presente)
    3. Fender Limit (Calcolato solo se fender_max_force / dati fender sono presenti)
    """
    angles = list(range(0, 360, 10))
    wind_line_limit = []
    
    # Verifico la disponibilità dei dati aggiuntivi nel dataframe
    has_bollard_swl = "bollard_swl" in geom_df.columns and geom_df["bollard_swl"].notna().any() and (geom_df["bollard_swl"] > 0).any()
    has_fender_data = "fender_max_force" in geom_df.columns and geom_df["fender_max_force"].notna().any() and (geom_df["fender_max_force"] > 0).any()

    wind_bollard_limit = [] if has_bollard_swl else None
    wind_fender_limit = [] if has_fender_data else None

    for angle in angles:
        # 1. Calcolo limite Cavi (Line Strength - Sempre Presente)
        speed_line = 5.0
        while speed_line <= 80.0:
            f = calculate_environmental_forces(speed_line, angle, v_curr, dir_curr, afw, alw, alc, loa)
            res = solve_line_tensions_3d(geom_df, f)
            if not res.empty and (res["Util_Percent"] > mbl_limit_pct).any():
                break
            speed_line += 2.0
        wind_line_limit.append(speed_line)

        # 2. Calcolo limite Bitte (Solo se presente bollard_swl)
        if has_bollard_swl:
            speed_bollard = 5.0
            while speed_bollard <= 80.0:
                f = calculate_environmental_forces(speed_bollard, angle, v_curr, dir_curr, afw, alw, alc, loa)
                res = solve_line_tensions_3d(geom_df, f)
                if "bollard_swl" in res.columns and (res["Tension_tons"] > res["bollard_swl"]).any():
                    break
                speed_bollard += 2.0
            wind_bollard_limit.append(speed_bollard)

        # 3. Calcolo limite Parabordi (Solo se presenti dati fender e vento verso la banchina)
        if has_fender_data:
            if 180 <= angle <= 360:
                # Simula la compressione limite dei parabordi
                speed_fender = 5.0
                while speed_fender <= 80.0:
                    f = calculate_environmental_forces(speed_fender, angle, v_curr, dir_curr, afw, alw, alc, loa)
                    # Verifica reazione trasversale di compressione contro i parabordi
                    f_transverse = abs(f.get("Fy_total_t", 0.0))
                    max_fender_capacity = geom_df["fender_max_force"].max()
                    if f_transverse > max_fender_capacity:
                        break
                    speed_fender += 2.0
                wind_fender_limit.append(speed_fender)
            else:
                wind_fender_limit.append(None)

    return angles, wind_line_limit, wind_bollard_limit, wind_fender_limit


def render_tab_polar():
    st.header("🌀 Inviluppo Polare di Operabilità Vento (360°)")
    st.caption("Analisi dinamica dei limiti di tenuta ormeggio secondo lo standard OCIMF MEG4 / Optimoor.")

    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    if geom_df.empty:
        st.warning("⚠️ Imposta prima la configurazione delle linee e della banchina nel layout.")
        return

    col1, col2 = st.columns(2)
    with col1:
        v_curr = st.number_input("Corrente (Knots)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)
    with col2:
        dir_curr = st.number_input("Direzione Corrente (°)", min_value=0, max_value=360, value=170, step=10)

    if st.button("🚀 Calcola Inviluppo Polare", use_container_width=True):
        with st.spinner("Calcolo delle curve di inviluppo in corso..."):
            
            afw = st.session_state.get("afw", 950.0)
            alw = st.session_state.get("alw", 3200.0)
            alc = st.session_state.get("alc", 1800.0)
            loa = st.session_state.get("loa", 323.44)

            angles, line_lim, bollard_lim, fender_lim = calculate_multi_limit_polar_envelope(
                geom_df, afw, alw, alc, loa, v_curr, dir_curr
            )

            fig = go.Figure()

            # CURVA 1: Line Strength (Rossa) - Sempre Tracciata
            angles_plot = angles + [360]
            line_plot = line_lim + [line_lim[0]]
            fig.add_trace(go.Scatterpolar(
                r=line_plot,
                theta=angles_plot,
                mode='lines',
                name='Wind for 50% Strength in any Line',
                line=dict(color='red', width=3)
            ))

            # CURVA 2: Bollard Strength (Verde/Ottanio) - Tracciata Solo Se Dati Disponibili
            if bollard_lim is not None:
                bollard_plot = bollard_lim + [bollard_lim[0]]
                fig.add_trace(go.Scatterpolar(
                    r=bollard_plot,
                    theta=angles_plot,
                    mode='lines',
                    name='Wind for Bollard Strength',
                    line=dict(color='#008080', width=2.5)
                ))

            # CURVA 3: Fender Limit (Gialla) - Tracciata Solo Se Dati Disponibili
            if fender_lim is not None:
                fender_plot = [f for f in fender_lim if f is not None]
                fender_angles = [a for a, f in zip(angles, fender_lim) if f is not None]
                if fender_plot:
                    fig.add_trace(go.Scatterpolar(
                        r=fender_plot,
                        theta=fender_angles,
                        mode='lines',
                        name='Wind for Fender Limit',
                        line=dict(color='#D4AC0D', width=2.5)
                    ))

            # Silhouette Nave al centro
            fig.add_trace(go.Scatterpolar(
                r=[0, 8, 0, 8, 0],
                theta=[0, 10, 180, 170, 0],
                mode='lines+fill',
                fill='toself',
                fillcolor='rgba(231, 76, 60, 0.4)',
                line=dict(color='darkred', width=1),
                name='Vessel Silhouette',
                showlegend=False
            ))

            fig.update_layout(
                template="plotly_white",
                polar=dict(
                    radialaxis=dict(
                        visible=True,
                        range=[0, 70],
                        tickvals=[12, 24, 36, 48, 60],
                        ticksuffix=" knt Wind",
                        angle=0,
                        showline=True
                    ),
                    angularaxis=dict(
                        direction="clockwise",
                        rotation=90,  # North / Prua in alto
                        tickvals=[0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330],
                        ticktext=["North", "30°", "60°", "90°", "120°", "150°", "South", "210°", "240°", "270°", "300°", "330°"]
                    )
                ),
                legend=dict(
                    x=0.70,
                    y=0.98,
                    bgcolor='rgba(255,255,255,0.85)',
                    bordercolor='Gray',
                    borderwidth=1
                ),
                margin=dict(l=40, r=40, t=40, b=40)
            )

            st.plotly_chart(fig, use_container_width=True)
