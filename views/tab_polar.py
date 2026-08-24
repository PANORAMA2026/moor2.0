"""
views/tab_polar.py
Interfaccia per la simulazione dell'inviluppo polare a 360 gradi.
"""

import streamlit as st
import plotly.express as px
from core.hydrodynamic_forces import generate_polar_envelope

def render_tab_polar():
    st.header("6. Inviluppo Polare Operativo")
    st.write("Valutazione dei limiti di sostenibilità del vento per ogni direzione attorno alla nave.")
    
    alw = st.session_state.get('alw', 2500.0)
    afw = st.session_state.get('afw', 600.0)
    lines_data = st.session_state.get('lines_data', [])
    
    if st.button("Calcola Diagramma Polare"):
        polar_data = generate_polar_envelope(lines_data, alw, afw)
        
        fig = px.line_polar(
            r=polar_data['max_winds'],
            theta=polar_data['angles'],
            start_angle=0,
            direction="clockwise",
            title="Massimo Vento Sostenibile [kts] (<55% MBL)"
        )
        st.plotly_chart(fig, use_container_width=True)
