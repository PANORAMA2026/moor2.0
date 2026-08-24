"""
app.py
Punto di ingresso principale dell'applicazione OpenMooring MEG4 Pro.
"""

import streamlit as st
from database.db_manager import init_db
from views.tab_ship_inventory import render_tab_ship_inventory
from views.tab_certificate import render_tab_certificate
from views.tab_simulation import render_tab_simulation
from views.tab_polar import render_tab_polar

# Inizializzazione della pagina e DB
st.set_page_config(page_title="OpenMooring MEG4 Pro", layout="wide")
init_db()

st.title("⚓ OpenMooring MEG4 Pro")

# Creazione delle schede dell'interfaccia
tab1, tab2, tab3, tab4 = st.tabs([
    "1. Dati Nave & Linee",
    "2. Certificati PDF",
    "3. Simulazione 3D",
    "4. Inviluppo Polare"
])

with tab1:
    render_tab_ship_inventory()

with tab2:
    render_tab_certificate()

with tab3:
    render_tab_simulation()

with tab4:
    render_tab_polar()
