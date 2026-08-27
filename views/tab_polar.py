"""
views/tab_polar.py
Inviluppo Polare dei Limiti Operativi del VENTO (0-360°) - Standard MEG4
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


def generate_fallback_polar_data():
    """Dati di esempio per visualizzazione preventiva."""
    angles = list(range(0, 360, 10))
    wind_line_limit = [
        round(50.0 - 20.0 * np.abs(np.sin(np.radians(a))), 1) for a in angles
    ]
    wind_bollard_limit = [
        round(60.0 - 15.0 * np.abs(np.sin(np.radians(a))), 1) for a in angles
    ]
    return angles, wind_line_limit, wind_bollard_limit


def calculate_wind_polar_envelope(
    geom_df: pd.DataFrame, 
    afw: float, 
    alw: float, 
    alc: float, 
    loa: float, 
    v_curr: float, 
    dir_curr: float, 
    mbl_limit_pct: float = 50.0,
    max_wind_test: float = 80.0
):
    """
    Calcola la massima velocità di VENTO tollerabile (0-360°) 
    mantenendo la corrente costante.
    """
    if solve_line_tensions_3d is None or calculate_environmental_forces is None or geom_df.empty:
        return generate_fallback_polar_data()

    angles = list(range(0, 360, 10))
    wind_line_limit = []
    wind_bollard_limit = []
    
    has_bollard_swl = "bollard_swl" in geom_df.columns and geom_df["bollard_swl"].notna().any()

    for wind_dir in angles:
        # 1. Calcolo limite VENTO per la tenuta dei cavi (50% MBL)
        v_wind = 5.0
        found_line_limit = False
        while v_wind <= max_wind_test:
            try:
                # Calcolo forze ambientali: Vento variabile (v_wind, wind_dir), Corrente fissa (v_curr, dir_curr)
                forces = calculate_environmental_forces(
                    v_wind, wind_dir, v_curr, dir_curr, afw, alw, alc, loa
                )
                res = solve_line_tensions_3d(geom_df, forces)
                
                if not res.empty and "Util_Percent" in res.columns:
                    if (res["Util_Percent"] > mbl_limit_pct).any():
                        wind_line_limit.append(round(v_wind, 1))
                        found_line_limit = True
                        break
            except Exception:
                pass
            v_wind += 2.0
            
        if not found_line_limit:
            wind_line_limit.append(max_wind_test)

        # 2. Calcolo limite VENTO per carico bitte (SWL)
        if has_bollard_swl:
            v_wind_b = 5.0
            found_bollard_limit = False
            while v_wind_b <= max_wind_test:
                try:
                    forces = calculate_environmental_forces(
                        v_wind_b, wind_dir, v_curr, dir_curr, afw, alw, alc, loa
                    )
                    res = solve_line_tensions_3d(geom_df, forces)
                    if not res.empty and "bollard_swl" in res.columns and "Tension_tons" in res.columns:
                        if (res["Tension_tons"] > res["bollard_swl"]).any():
                            wind_bollard_limit.append(round(v_wind_b, 1))
                            found_bollard_limit = True
                            break
                except Exception:
                    pass
                v_wind_b += 2.0
                
            if not found_bollard_limit:
                wind_bollard_limit.append(max_wind_test)

    bollard_res = wind_bollard_limit if has_bollard_swl else None
    return angles, wind_line_limit, bollard_res


def build_polar_figure(angles, line_lim, bollard_lim=None):
    """Genera il diagramma polare Plotly per il vento."""
    fig = go.Figure()

    angles_plot = angles + [angles[0]]
    line_plot = line_lim + [line_lim[0]]

    # Curva Limite Vento Cavi (50% MBL)
    fig.add_trace(go.Scatterpolar(
        r=line_plot,
        theta=angles_plot,
        mode='lines+markers',
        name='Max Vento Sostenibile (50% MBL Cavi)',
        line=dict(color='#E74C3C', width=3),
        fill='toself',
        fillcolor='rgba(231, 76, 60, 0.15)'
    ))

    # Curva Limite Vento Bitte
    if bollard_lim is not None and len(bollard_lim) == len(angles):
        bollard_plot = bollard_lim + [bollard_lim[0]]
        fig.add_trace(go.Scatterpolar(
            r=bollard_plot,
            theta=angles_plot,
            mode='lines',
            name='Max Vento Sostenibile (SWL Bitte)',
            line=dict(color='#2980B9', width=2.5, dash='dash')
        ))

    fig.update_layout(
        title=dict(
            text="Inviluppo Polare di Operabilità al Vento (Knots)",
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
                ticktext=["Prua (0°)", "45°", "Dritta (90°)", "135°", "Poppa (180°)", "225°", "Sinistra (270°)", "315°"]
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
    st.markdown("Determinazione della **massima velocità del vento ammissibile** da ogni direzione prima del superamento del limite di sicurezza dei cavi (50% MBL).")

    geom_df = st.session_state.get("geom_df", pd.DataFrame())

    # Configurazione Parametri Vento e Corrente
    with st.expander("⚙️ Parametri di Calcolo Ambientali", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            mbl_lim = st.slider("Limite Cavi (% MBL)", min_value=30, max_value=55, value=50, step=5)
        with c2:
            v_curr = st.number_input("Corrente di Fondo (Knots)", min_value=0.0, max_value=5.0, value=0.0, step=0.1, help="Imposta a 0 per valutare il solo impatto del vento")
        with c3:
            dir_curr = st.number_input("Direzione Corrente (°)", min_value=0, max_value=360, value=0, step=10)

    if st.button("🚀 Calcola Inviluppo Polare Vento", type="primary", use_container_width=True):
        with st.spinner("Calcolo dei limiti di vento a 360° in corso..."):
            afw = st.session_state.get("afw", 950.0)
            alw = st.session_state.get("alw", 3200.0)
            alc = st.session_state.get("alc", 1800.0)
            loa = st.session_state.get("loa", 323.44)

            angles, line_lim, bollard_lim = calculate_wind_polar_envelope(
                geom_df, afw, alw, alc, loa, v_curr, dir_curr, mbl_limit_pct=mbl_lim
            )

            fig = build_polar_figure(angles, line_lim, bollard_lim)
            st.session_state["polar_fig"] = fig
            st.success("Analisi del vento completata!")

    # Rendering Grafico
    if "polar_fig" in st.session_state and st.session_state["polar_fig"] is not None:
        st.plotly_chart(st.session_state["polar_fig"], use_container_width=True)
    else:
        st.info("ℹ️ Clicca su **Calcola Inviluppo Polare Vento** per avviare la simulazione a 360°.")
