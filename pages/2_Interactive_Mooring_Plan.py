import streamlit as st

from views.tab_mooring_plan import render_tab_mooring_plan

st.set_page_config(page_title="Interactive Mooring Plan", layout="wide")

# Keep this first proof-of-concept independent from the legacy tab until the
# geometry model has been validated against the real station plans.
port_options = [
    "Long Beach Cruise Terminal",
    "Mazatlan Pier 4/5",
    "Mazatlan Pier 2/3",
    "La Paz",
    "Ensenada Pier #2",
    "Puerto Vallarta Pier #1",
    "Puerto Vallarta Pier #3",
]
selected_port = st.sidebar.selectbox("📌 Shore bollard database", port_options)

render_tab_mooring_plan(selected_port=selected_port)
