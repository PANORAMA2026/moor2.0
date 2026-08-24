# views/tab_simulation.py
import streamlit as st
from core.hydrodynamic_forces import calculate_wind_force, calculate_current_force

def render_tab(ship_data):
    st.header("⚡ Simulatore Forze d'Ormeggio")
    
    col1, col2 = st.columns(2)
    with col1:
        wind_speed = st.slider("Velocità Vento [kts]", 0, 60, 25)
        wind_angle = st.slider("Direzione Vento [°]", 0, 360, 45)
    
    with col2:
        current_speed = st.slider("Velocità Corrente [kts]", 0.0, 5.0, 1.2)
        current_angle = st.slider("Direzione Corrente [°]", 0, 360, 90)
        
    if st.button("Calcola Carichi Ambientali"):
        fx_w, fy_w, mz_w = calculate_wind_force(
            wind_speed, wind_angle, 
            ship_data["front_area"], ship_data["side_area"]
        )
        fx_c, fy_c, mz_c = calculate_current_force(
            current_speed, current_angle, 
            ship_data["draft"], ship_data["loa"]
        )
        
        st.subheader("Risultati Carichi Vento & Corrente")
        st.write(f"**Forza Longitudinale Totale (Fx):** {fx_w + fx_c:.2f} kN")
        st.write(f"**Forza Trasversale Totale (Fy):** {fy_w + fy_c:.2f} kN")
        st.write(f"**Momento d'Imbardata Totale (Mz):** {mz_w + mz_c:.2f} kNm")
