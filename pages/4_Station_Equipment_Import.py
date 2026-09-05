import streamlit as st
from core.mooring_geometry import init_mooring_geometry_db, get_components
from core.station_seed import seed_fwd, seed_aft

st.set_page_config(page_title="Station Equipment Import", layout="wide")
init_mooring_geometry_db()

st.title("🔧 Mooring Station Equipment — Drawing Register")
st.caption("Equipment identification is taken from the supplied technical drawing. Coordinates are intentionally left N/D until calibrated/mapped.")

station = st.selectbox("Station", ["Prua (Forward Station)", "Poppa (Aft Station)"])
if station == "Prua (Forward Station)":
    if st.button("Import FWD equipment from drawing", type="primary"):
        n = seed_fwd(station)
        st.success(f"Imported {n} source-identified equipment records.")
        st.rerun()
else:
    if st.button("Import AFT equipment from drawing", type="primary"):
        n = seed_aft(station)
        st.success(f"Imported {n} source-identified equipment records.")
        st.rerun()

df = get_components(station)
if df.empty:
    st.info("No equipment imported yet.")
else:
    cols = ["component_id","component_type","source_item","source_piece_number","source_drawing","plan_x_px","plan_y_px","x_m","y_m","z_m","diameter_mm"]
    st.dataframe(df[cols], use_container_width=True, hide_index=True)
    st.metric("Registered components", len(df))
    st.warning("N/D coordinates are expected at this stage. Do not use the geometry for engineering calculations until the station mapping and XYZ coordinates are verified.")
