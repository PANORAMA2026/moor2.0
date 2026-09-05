import streamlit as st

from core.mooring_geometry import init_mooring_geometry_db, get_components, get_connections
from core.mooring_route import validate_station
from core.station_seed import seed_fwd, seed_aft

st.set_page_config(page_title="Mooring Geometry Audit", layout="wide")
init_mooring_geometry_db()

st.title("🔎 Mooring Geometry Audit")
st.caption("Engineering audit of the persistent 2D/3D mooring configuration. Missing data is reported explicitly; no coordinates are inferred here.")

station = st.selectbox("Station", ["Prua (Forward Station)", "Poppa (Aft Station)"])

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("Import source equipment", use_container_width=True):
        count = seed_fwd(station) if station.startswith("Prua") else seed_aft(station)
        st.success(f"Source catalogue imported: {count} components.")
        st.rerun()
with c2:
    components = get_components(station)
    st.metric("Components", len(components))
with c3:
    connections = get_connections(station)
    st.metric("Configured lines", len(connections))

if not components.empty:
    st.subheader("Equipment source register")
    cols = ["component_id", "component_type", "source_item", "source_piece_number", "source_drawing", "plan_x_px", "plan_y_px", "x_m", "y_m", "z_m", "diameter_mm"]
    st.dataframe(components[cols], use_container_width=True, hide_index=True)

st.subheader("Line route audit")
audit = validate_station(station)
if audit.empty:
    st.info("No mooring line routes have been configured yet.")
else:
    st.dataframe(audit, use_container_width=True, hide_index=True)
    errors = int((audit.status == "ERROR").sum())
    warnings = int((audit.status == "WARNING").sum())
    ok = int((audit.status == "OK").sum())
    st.write(f"**Status:** {ok} OK · {warnings} warnings · {errors} errors")

st.info("Next engineering inputs will be the real station coordinates/geometry and fairlead diameters. Until then, the audit intentionally leaves those fields as N/D rather than creating synthetic values.")
