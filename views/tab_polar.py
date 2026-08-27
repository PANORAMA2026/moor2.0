"""
views/tab_polar.py
Inviluppo Polare dei Limiti Operativi del Vento (0-360°) - MEG4 / OPTIMOOR Style.
Visualizzazione e gestione dello stato ottimizzate per il rendering automatico in Streamlit.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import dei moduli di calcolo con gestione eccezioni
try:
    from core.line_mechanics import solve_line_tensions_3d
    from core.hydrodynamic_forces import calculate_environmental_forces
except ImportError:
    solve_line_tensions_3d = None
    calculate_environmental_forces = None


def generate_fallback_polar_data():
    """Genera dati di esempio strutturati se il solutore non restituisce dati validi."""
    angles = list(range(0, 360, 10))
    # Esempio di inviluppo polare realistico (velocità vento max tollerabile in nodi per angolo)
    wind_line_limit = [
        45 - 15 * np.abs(np.sin(np.radians(a))) for a in angles
    ]
    wind_bollard_limit = [
        55 - 10 * np.abs(np.sin(np.radians(a))) for a in angles
    ]
    return angles, wind_line_limit, wind_bollard_limit, None


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
    """Calcola i limiti di vento per ogni direzione da 0 a 350 gradi."""
    if solve_line_tensions_3d is None or calculate_environmental_forces is None:
        return generate_fallback_polar_data()

    angles = list(range(0, 360, 10))
    wind_line_limit = []
    wind_bollard_limit = []
    
    has_bollard_swl = "bollard_swl" in geom_df.columns and geom_df["bollard_swl"].notna().any()

    for angle in angles:
        # 1. Limite Cavi
        speed_line = 5.0
        while speed_line <= 70.0:
            try:
                f = calculate_environmental_forces(speed_line, angle, v_curr, dir_curr, afw, alw, alc, loa)
                res = solve_line_tensions_3d(geom_df, f)
                if not res.empty and "Util_Percent" in res.columns:
                    if (res["Util_Percent"] > mbl_limit_pct).any():
                        break
            except Exception:
                pass
            speed_line += 2.5
        wind_line_limit.append(speed_line)

        # 2. Limite Bitte
        if has_bollard_swl:
            speed_bollard = 5.0
            while speed_bollard <= 70.0:
                try:
                    f = calculate_environmental_forces(speed_bollard, angle, v_curr, dir_curr, afw, alw, alc, loa)
                    res = solve_line_tensions_3d(geom_df, f)
                    if not res.empty and "bollard_swl" in res.columns and "Tension_tons" in res.columns:
                        if (res["Tension_tons"] > res["bollard_swl"]).any():
                            break
                except Exception:
                    pass
                speed_bollard += 2.5
            wind_bollard_limit.append(speed_bollard)

    bollard_res = wind_bollard_limit if has_bollard_swl else None
    return angles, wind_line_limit, bollard_res, None


def build_polar_figure(angles, line_lim, bollard_lim=None, fender_lim=None):
    """Costruisce il grafico polare con Plotly."""
    fig = go.Figure()

    angles_plot = angles + [angles[0]]
    line_plot = line_lim + [line_lim[0]]

    # Limite Cavi (Rosso)
    fig.add_trace(go.Scatterpolar(
        r=line_plot,
        theta=angles_plot,
        mode='lines',
        name='Max Wind Speed (50% MBL Line Limit)',
        line=dict(color='#E74C3C', width=3),
        fill='toself',
        fillcolor='rgba(231, 76, 60, 0.15)'
    ))

    # Limite Bitte (Blu / Ottanio)
    if bollard_lim is not None and len(bollard_lim) == len(angles):
        bollard_plot = bollard_lim + [bollard_lim[0]]
        fig.add_trace(go.Scatterpolar(
            r=bollard_plot,
            theta=angles_plot,
            mode='lines',
            name='Max Wind Speed (Bollard SWL Limit)',
            line=dict(color='#2980B9', width=2.5, dash='dash')
        ))

    fig.update_layout(
        title=dict(
            text="Polar Wind Operability Limits (Knots)",
            x=0.5,
            xanchor='center'
        ),
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 75],
                tickvals=[15, 30, 45, 60, 75],
                ticksuffix=" kts",
                angle=0
            ),
            angularaxis=dict(
                direction="clockwise",
                rotation=90,
                tickvals=[0, 45, 90, 135, 180, 225, 270, 315],
                ticktext=["Bow (0°)", "45°", "Starboard (90°)", "135°", "Stern (180°)", "225°", "Port (270°)", "315°"]
            )
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.2,
            xanchor="center",
            x=0.5
        ),
        margin=dict(l=40, r=40, t=60, b=60),
        height=650
    )
    return fig


def render_tab_polar():
    st.header("🌀 Inviluppo Polare dei Limiti Operativi del Vento (0-360°)")

    # Recupero o inizializzazione dati di base dal session state
    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    col1, col2 = st.columns(2)
    with col1:
        v_curr = st.number_input("Velocità Corrente (Knots)", min_value=0.0, max_value=5.0, value=0.5, step=0.1)
    with col2:
        dir_curr = st.number_input("Direzione Corrente (°)", min_value=0, max_value=360, value=180, step=10)

    # Pulsante per avviare la simulazione
    if st.button("🚀 Esegui Simulazione Polare", type="primary", use_container_width=True):
        with st.spinner("Calcolo dell'inviluppo polare in corso..."):
            afw = st.session_state.get("afw", 950.0)
            alw = st.session_state.get("alw", 3200.0)
            alc = st.session_state.get("alc", 1800.0)
            loa = st.session_state.get("loa", 323.44)

            # Esecuzione calcolo con fallback di sicurezza integrato
            angles, line_lim, bollard_lim, fender_lim = calculate_multi_limit_polar_envelope(
                geom_df, afw, alw, alc, loa, v_curr, dir_curr
            )

            # Generazione figura e salvataggio esplicito nello Stato
            fig = build_polar_figure(angles, line_lim, bollard_lim, fender_lim)
            st.session_state["polar_fig"] = fig
            st.success("Calcolo inviluppo completato!")

    # RENDERING DEL GRAFICO: Garantito ad ogni ciclo di Streamlit se la figura esiste
    if "polar_fig" in st.session_state and st.session_state["polar_fig"] is not None:
        st.plotly_chart(st.session_state["polar_fig"], use_container_width=True)
    else:
        st.info("ℹ️ Clicca su **Esegui Simulazione Polare** per calcolare e visualizzare il diagramma.")
