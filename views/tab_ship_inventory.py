"""
views/tab_ship_inventory.py
Interfaccia per la gestione delle dimensioni della nave e inventario linee.
"""

import streamlit as st
import pandas as pd

def render_tab_ship_inventory():
    st.header("1. Dimensioni Nave & Inventario Linee")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Caratteristiche Scafo")
        loa = st.number_input("Lunghezza Fuori Tutto (LOA) [m]", value=st.session_state.get('loa', 200.0))
        beam = st.number_input("Larghezza (Beam) [m]", value=st.session_state.get('beam', 32.0))
        st.session_state['loa'] = loa
        st.session_state['beam'] = beam

    with col2:
        st.subheader("Superfici Esposte (MEG4)")
        alw = st.number_input("Superficie Laterale Vento (ALW) [m²]", value=st.session_state.get('alw', 2500.0))
        afw = st.number_input("Superficie Frontale Vento (AFW) [m²]", value=st.session_state.get('afw', 600.0))
        st.session_state['alw'] = alw
        st.session_state['afw'] = afw

    st.markdown("---")
    st.subheader("Inventario Cavi d'Ormeggio")
    
    default_lines = [
        {"id": "HEAD_1", "mbl": 120.0, "diameter": 64, "x_chock": 95.0, "y_chock": 14.0},
        {"id": "HEAD_2", "mbl": 120.0, "diameter": 64, "x_chock": 95.0, "y_chock": 14.0},
        {"id": "STERN_1", "mbl": 120.0, "diameter": 64, "x_chock": -95.0, "y_chock": 14.0},
        {"id": "STERN_2", "mbl": 120.0, "diameter": 64, "x_chock": -95.0, "y_chock": 14.0},
    ]
    
    df_lines = pd.DataFrame(st.session_state.get('lines_data', default_lines))
    edited_df = st.data_editor(df_lines, num_rows="dynamic", key="inventory_editor")
    st.session_state['lines_data'] = edited_df.to_dict('records')
