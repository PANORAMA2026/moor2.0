# views/tab_ship_inventory.py
import streamlit as st

def render_tab():
    st.header("🚢 Dati Nave & Inventario Linee")
    
    col1, col2 = st.columns(2)
    with col1:
        length = st.number_input("Lunghezza Fuori Tutto (LOA) [m]", value=200.0)
        beam = st.number_input("Larghezza (Beam) [m]", value=32.0)
        draft = st.number_input("Pescaggio (Draft) [m]", value=10.0)
    
    with col2:
        front_area = st.number_input("Area Frontale Vento [m²]", value=450.0)
        side_area = st.number_input("Area Laterale Vento [m²]", value=1800.0)
        
    return {
        "loa": length,
        "beam": beam,
        "draft": draft,
        "front_area": front_area,
        "side_area": side_area
    }
