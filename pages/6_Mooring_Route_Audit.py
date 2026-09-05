import sqlite3
import pandas as pd
import streamlit as st

from config.constants import DB_FILE_PATH
from core.mooring_route_engine import analyze_route
from core.mooring_geometry import get_connections

PORTS = [
    "Long Beach Cruise Terminal", "Mazatlan Pier 4/5", "Mazatlan Pier 2/3",
    "La Paz", "Ensenada Pier #2", "Puerto Vallarta Pier #1", "Puerto Vallarta Pier #3",
]
STATIONS = ["Prua (Forward Station)", "Poppa (Aft Station)"]


def set_line_port(station, line_id, port_name):
    conn=sqlite3.connect(DB_FILE_PATH)
    conn.execute("UPDATE mooring_connections SET port_name=? WHERE station_name=? AND line_id=?",(port_name,station,line_id))
    conn.commit(); conn.close()

st.set_page_config(page_title="Mooring Route Audit", layout="wide")
st.title("🔎 Mooring Route Audit")
st.caption("Verifica della connettività e della geometria. Nessun valore di tensione viene inventato.")

station=st.selectbox("Station",STATIONS)
connections=get_connections(station)
if connections.empty:
    st.info("Nessuna linea configurata per questa stazione.")
    st.stop()

line_ids=connections.line_id.astype(str).tolist()
line_id=st.selectbox("Line",line_ids)
current=connections[connections.line_id.astype(str)==line_id].iloc[0]
port=st.selectbox("Shore port",PORTS,index=PORTS.index(current.port_name) if pd.notna(current.port_name) and current.port_name in PORTS else 0)
if st.button("Save port assignment", type="primary"):
    set_line_port(station,line_id,port)
    st.success(f"{line_id} assegnata a {port}.")
    st.rerun()

result=analyze_route(station,line_id)
st.subheader(f"Line {line_id}")
status=result.get("status")
if status=="COMPLETE": st.success("Geometry complete")
else: st.warning("Geometry incomplete")

c1,c2,c3=st.columns(3)
c1.metric("Line length", "N/D" if result.get("line_length_m") is None else f"{result['line_length_m']:.2f} m")
c2.metric("Missing coordinates", str(len(result.get("missing_coordinates",[]))))
c3.metric("Route nodes", str(len(result.get("nodes",[]))))

if result.get("missing_coordinates"):
    st.error("Dati mancanti: " + ", ".join(result["missing_coordinates"]))

rows=[]
for n in result.get("nodes",[]):
    rows.append({"Seq":n["sequence"],"Component":n["component_id"],"Coordinate":n["coordinate_status"],"XYZ":n.get("point")})
st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

if result.get("direction_changes"):
    st.subheader("Automatic direction changes")
    st.dataframe(pd.DataFrame(result["direction_changes"]),use_container_width=True,hide_index=True)

contact=result.get("fairlead_contact")
if contact:
    st.subheader("Fairlead contact geometry")
    st.write(f"**Status:** {contact.get('status','N/D')}")
    if contact.get("contact_angle_deg") is not None:
        st.metric("Planar contact angle", f"{contact['contact_angle_deg']:.2f}°")
    st.caption(contact.get("note","Geometry only; no friction/capstan correction."))
else:
    st.info("Fairlead contact geometry not yet available: fairlead diameter/axis and complete XYZ route are required.")

st.subheader("Engineering interpretation")
st.write("The audit reports geometry only. It does not convert contact angle into tension amplification and does not apply a friction coefficient unless a separately justified model is added.")
