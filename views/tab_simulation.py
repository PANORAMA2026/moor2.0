"""
views/tab_simulation.py
Interfaccia di simulazione tensioni 3D e calcolo parametri ambientali.
"""

import streamlit as st
import numpy as np
from utils.telemetry import calculate_bollard_coords
from core.line_mechanics import build_global_stiffness_matrix, solve_line_tensions
from core.hydrodynamic_forces import calculate_wind_forces
from utils.rendering_3d import plot_3d_mooring_system

def render_tab_simulation():
    st.header("5. Simulazione Tensioni & Visualizzazione 3D")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Condizioni Ambientali")
        wind_speed = st.slider("Velocità Vento [kts]", 0.0, 70.0, 25.0)
        wind_angle = st.slider("Direzione Vento [° relative]", 0, 360, 45)
    
    with col2:
        st.subheader("Rilevamento Telemetrico Banchina")
        dist = st.number_input("Distanza Telemetro [m]", value=35.0)
        pitch = st.number_input("Pendenza [°]", value=5.0)
        azimuth = st.number_input("Azimuth [°]", value=30.0)

    loa = st.session_state.get('loa', 200.0)
    beam = st.session_state.get('beam', 32.0)
    alw = st.session_state.get('alw', 2500.0)
    afw = st.session_state.get('afw', 600.0)

    # Calcolo delle forze esterne agenti
    fx, fy, mz = calculate_wind_forces(wind_speed, wind_angle, alw, afw)
    ext_forces = np.array([fx, fy, mz])
    
    lines_data = st.session_state.get('lines_data', [])
    
    # Assegnazione di rigidezze fittizie e posizioni bitta per il calcolo
    for line in lines_data:
        line['k_eq'] = 150.0  # Rigidezza equivalente fittizia
        line['azimuth'] = azimuth
        line['elevation'] = pitch
        line['x_bollard'] = line['x_chock'] + 20.0
        line['y_bollard'] = line['y_chock'] + 15.0

    k_glob = build_global_stiffness_matrix(lines_data)
    results = solve_line_tensions(ext_forces, k_glob, lines_data)
    
    for i, res in enumerate(results):
        lines_data[i]['pct_mbl'] = res['pct_mbl']
        lines_data[i]['tension_tons'] = res['tension_tons']

    st.markdown("---")
    st.subheader("Tensiostruttura 3D")
    fig = plot_3d_mooring_system(loa, beam, lines_data, bollards_data=[])
    st.plotly_chart(fig, use_container_width=True)
