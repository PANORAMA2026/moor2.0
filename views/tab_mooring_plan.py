"""Interactive mooring station plan and synchronized 3D proof of concept."""

import math
import os
import sqlite3

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from config.constants import DB_FILE_PATH, DEFAULT_SHIP
from database.db_manager import load_certificates_from_db, load_lines_inventory_from_db
from core.mooring_geometry import (
    COMPONENT_TYPES, init_mooring_geometry_db, get_components, get_connections,
    get_line_detail, seed_station_from_aft_catalog, upsert_component,
    delete_component, upsert_connection,
)

STATIONS = ["Prua (Forward Station)", "Poppa (Aft Station)"]
PLANS_DIR = os.path.join("assets", "planimetrie")


def _conn():
    conn = sqlite3.connect(DB_FILE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _station_image_path(station):
    conn = _conn()
    row = conn.execute("SELECT image_path FROM station_metadata WHERE station_name=?", (station,)).fetchone()
    conn.close()
    if row and row["image_path"] and os.path.exists(row["image_path"]):
        return row["image_path"]
    return None


def _save_station_image(station, data, extension):
    os.makedirs(PLANS_DIR, exist_ok=True)
    safe = station.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_")
    path = os.path.join(PLANS_DIR, f"{safe}{extension}")
    with open(path, "wb") as f:
        f.write(data)
    conn = _conn()
    conn.execute(
        "INSERT INTO station_metadata(station_name,image_path) VALUES(?,?) "
        "ON CONFLICT(station_name) DO UPDATE SET image_path=excluded.image_path",
        (station, path),
    )
    conn.commit(); conn.close()
    return path


def _bollards(port):
    if not port:
        return pd.DataFrame()
    conn = _conn()
    df = pd.read_sql_query(
        "SELECT bollard_id,x_m,y_m,z_m,swl_t,stato FROM port_bollards WHERE port_name=?",
        conn, params=(port,),
    )
    conn.close()
    return df


def _nearest_component(df, x, y, threshold=35):
    best, best_d = None, threshold
    for _, r in df.iterrows():
        if pd.isna(r.plan_x_px) or pd.isna(r.plan_y_px):
            continue
        d = math.hypot(float(r.plan_x_px)-x, float(r.plan_y_px)-y)
        if d < best_d:
            best, best_d = str(r.component_id), d
    return best


def _point_to_segment(px, py, ax, ay, bx, by):
    vx, vy = bx-ax, by-ay
    den = vx*vx + vy*vy
    if den == 0:
        return math.hypot(px-ax, py-ay)
    t = max(0.0, min(1.0, ((px-ax)*vx + (py-ay)*vy)/den))
    qx, qy = ax+t*vx, ay+t*vy
    return math.hypot(px-qx, py-qy)


def _nearest_line(components, connections, x, y, threshold=20):
    lookup = {str(r.component_id): r for r in components.itertuples()}
    best, best_d = None, threshold
    for r in connections.itertuples():
        w, f = lookup.get(str(r.winch_id)), lookup.get(str(r.fairlead_id))
        if not w or not f or any(pd.isna(v) for v in [w.plan_x_px,w.plan_y_px,f.plan_x_px,f.plan_y_px]):
            continue
        d = _point_to_segment(x,y,float(w.plan_x_px),float(w.plan_y_px),float(f.plan_x_px),float(f.plan_y_px))
        if d < best_d:
            best, best_d = str(r.line_id), d
    return best


def _draw_plan(image, components, connections, selected_component=None, selected_line=None):
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    lookup = {str(r.component_id): r for r in components.itertuples()}
    for r in connections.itertuples():
        w, f = lookup.get(str(r.winch_id)), lookup.get(str(r.fairlead_id))
        if not w or not f or any(pd.isna(v) for v in [w.plan_x_px,w.plan_y_px,f.plan_x_px,f.plan_y_px]):
            continue
        selected = str(r.line_id) == str(selected_line)
        draw.line([(int(w.plan_x_px),int(w.plan_y_px)),(int(f.plan_x_px),int(f.plan_y_px))], fill=(220,40,40) if selected else (40,110,220), width=7 if selected else 3)
        draw.text((int((w.plan_x_px+f.plan_x_px)/2)+4,int((w.plan_y_px+f.plan_y_px)/2)+4),str(r.line_id),fill=(20,20,20))
    for r in components.itertuples():
        if pd.isna(r.plan_x_px) or pd.isna(r.plan_y_px):
            continue
        selected = str(r.component_id) == str(selected_component)
        rad = 11 if selected else 6
        draw.ellipse((r.plan_x_px-rad,r.plan_y_px-rad,r.plan_x_px+rad,r.plan_y_px+rad), outline=(220,40,40) if selected else (20,20,20), width=3)
        draw.text((r.plan_x_px+10,r.plan_y_px-10),str(r.component_id),fill=(20,20,20))
    return canvas


def _render_3d(station, port):
    import plotly.graph_objects as go
    from config.constants import DEFAULT_SHIP

    components, connections, bollards = get_components(station), get_connections(station), _bollards(port)
    fig = go.Figure()

    # Visualization-only ship envelope from principal dimensions. It is NOT used by
    # the engineering solver until an approved vessel geometry model is available.
    L = float(DEFAULT_SHIP.get("LOA", 323.44)); B = float(DEFAULT_SHIP.get("Beam", 37.20))
    x = [-L/2, -L*0.35, 0, L*0.35, L/2]
    half_beam = [0.0, B/2*0.92, B/2, B/2*0.92, 0.0]
    for side in (-1, 1):
        fig.add_trace(go.Scatter3d(x=x,y=[side*v for v in half_beam],z=[0,0,0,0,0],mode="lines",line=dict(width=4),name="Ship envelope" if side==1 else None,showlegend=side==1,hoverinfo="skip"))

    valid = components.dropna(subset=["x_m","y_m","z_m"])
    if not valid.empty:
        fig.add_trace(go.Scatter3d(x=valid.x_m,y=valid.y_m,z=valid.z_m,mode="markers+text",text=valid.component_id,textposition="top center",marker=dict(size=6),name="Ship components"))

    comp = {str(r.component_id):r for r in components.itertuples()}
    shore = {str(r.bollard_id):r for r in bollards.itertuples()}
    for r in connections.itertuples():
        w,f,b=comp.get(str(r.winch_id)),comp.get(str(r.fairlead_id)),shore.get(str(r.bollard_id))
        if not w or not f or not b: continue
        vals=[w.x_m,w.y_m,w.z_m,f.x_m,f.y_m,f.z_m,b.x_m,b.y_m,b.z_m]
        if any(pd.isna(v) for v in vals): continue
        selected = str(r.line_id) == str(st.session_state.get("mooring_selected_line"))
        fig.add_trace(go.Scatter3d(x=[w.x_m,f.x_m,b.x_m],y=[w.y_m,f.y_m,b.y_m],z=[w.z_m,f.z_m,b.z_m],mode="lines+markers",line=dict(width=9 if selected else 5),name=f"Line {r.line_id}"))

    if not bollards.empty:
        fig.add_trace(go.Scatter3d(x=bollards.x_m,y=bollards.y_m,z=bollards.z_m,mode="markers+text",text=bollards.bollard_id,marker=dict(size=7,symbol="diamond"),name="Shore bollards"))

    fig.update_layout(height=650,margin=dict(l=0,r=0,t=40,b=0),scene=dict(aspectmode="data",xaxis_title="X (m)",yaxis_title="Y (m)",zaxis_title="Z (m)"),title=f"3D Mooring Geometry — {station}")
    st.plotly_chart(fig,use_container_width=True)
    st.caption("Lo scafo mostrato qui è un envelope visuale basato sulle dimensioni principali; non viene usato per il calcolo delle forze.")


def render_tab_mooring_plan(selected_port=None):
    init_mooring_geometry_db()
    st.header("🏗️ Interactive Mooring Station Plan")
    st.caption("Reference drawing + engineering database + synchronized 3D view.")
    station=st.selectbox("Mooring Station",STATIONS,key="interactive_station")

    c0,c1,c2=st.columns([1.2,1.2,2])
    with c0:
        if station == "Poppa (Aft Station)" and st.button("📥 Import AFT drawing equipment",use_container_width=True):
            n=seed_station_from_aft_catalog(station)
            st.success(f"Importati {n} componenti identificati dal drawing. Le coordinate restano N/D finché non vengono mappate.")
            st.rerun()
    with c1:
        if st.button("🔄 Recalculate geometry",use_container_width=True):
            from core.mooring_geometry import recalculate_all
            recalculate_all(station); st.rerun()
    with c2:
        st.info("Il catalogo identifica gli equipment dal drawing; non assegna coordinate inventate.")

    path=_station_image_path(station)
    upload=st.file_uploader("Carica il pianetto reale della stazione",type=["png","jpg","jpeg"],key=f"plan_upload_{station}")
    if upload:
        _,ext=os.path.splitext(upload.name); _save_station_image(station,upload.getvalue(),ext.lower() or ".png"); st.success("Pianetto salvato."); st.rerun()
    if not path:
        st.info("Nessun pianetto salvato per questa stazione. Carica il drawing reale per iniziare il mapping.")
        return

    image=Image.open(path); components=get_components(station); connections=get_connections(station)
    selected_component=st.session_state.get("mooring_selected_component"); selected_line=st.session_state.get("mooring_selected_line")
    left,right=st.columns([2.2,1])
    with left:
        click=streamlit_image_coordinates(_draw_plan(image,components,connections,selected_component,selected_line),key=f"plan_click_{station}")
        if click:
            x,y=float(click["x"]),float(click["y"])
            lid=_nearest_line(components,connections,x,y)
            cid=_nearest_component(components,x,y)
            if lid:
                st.session_state.mooring_selected_line=lid; st.session_state.mooring_selected_component=None; st.rerun()
            if cid:
                st.session_state.mooring_selected_component=cid; st.session_state.mooring_selected_line=None; st.rerun()
            st.session_state.pending_px=x; st.session_state.pending_py=y

    with right:
        if selected_line:
            detail=get_line_detail(station,selected_line)
            st.subheader(f"🔗 Line {selected_line}")
            st.write(f"**Winch:** {detail.get('Winch','N/D')}")
            st.write(f"**Fairlead:** {detail.get('Fairlead','N/D')}")
            st.write(f"**Bollard:** {detail.get('Bollard','N/D')}")
            angle=detail.get('centerline_angle_deg')
            st.metric("Centerline direction change", "N/D" if angle is None or pd.isna(angle) else f"{float(angle):.1f}°")
            st.caption("Il contact/wrap angle della fairlead non viene inventato; sarà calcolato dopo la geometria reale della fairlead.")
        elif selected_component:
            row=components[components.component_id.astype(str)==str(selected_component)]
            if not row.empty:
                r=row.iloc[0]
                st.subheader(f"⚙️ {r.component_id}")
                st.write(f"**Type:** {r.component_type}")
                st.write(f"**Source item:** {r.source_item if pd.notna(r.source_item) else 'N/D'}")
                st.write(f"**Piece number:** {r.source_piece_number or 'N/D'}")
                st.write(f"**Plan:** ({r.plan_x_px if pd.notna(r.plan_x_px) else 'N/D'}, {r.plan_y_px if pd.notna(r.plan_y_px) else 'N/D'}) px")
                st.write(f"**XYZ:** ({r.x_m if pd.notna(r.x_m) else 'N/D'}, {r.y_m if pd.notna(r.y_m) else 'N/D'}, {r.z_m if pd.notna(r.z_m) else 'N/D'}) m")
                st.write(f"**Diameter:** {r.diameter_mm if pd.notna(r.diameter_mm) else 'N/D'} mm")

        st.subheader("Add / edit component")
        cid=st.text_input("Component ID",value=selected_component or "")
        ctype=st.selectbox("Type",COMPONENT_TYPES)
        p1,p2=st.columns(2)
        with p1:
            px=st.number_input("Plan X px",value=float(st.session_state.get("pending_px",0.0)))
            x=st.number_input("Ship X m",value=0.0)
            z=st.number_input("Ship Z m",value=0.0)
        with p2:
            py=st.number_input("Plan Y px",value=float(st.session_state.get("pending_py",0.0)))
            y=st.number_input("Ship Y m",value=0.0)
            diameter=st.number_input("Diameter mm",min_value=0.0,value=0.0)
        if st.button("💾 Save component",use_container_width=True) and cid.strip():
            upsert_component(station,cid.strip(),ctype,px,py,x,y,z,diameter)
            st.session_state.mooring_selected_component=cid.strip(); st.rerun()
        if selected_component and st.button("🗑️ Delete component",use_container_width=True):
            delete_component(station,selected_component); st.session_state.mooring_selected_component=None; st.rerun()

    st.divider(); st.subheader("🔗 Line connectivity")
    inv=load_lines_inventory_from_db(); lines=inv.line_id.astype(str).tolist() if not inv.empty else []
    winches=components[components.component_type=="WINCH"].component_id.astype(str).tolist() if not components.empty else []
    fairleads=components[components.component_type.isin(["FAIRLEAD","CHOCK","CAPSTAN"])].component_id.astype(str).tolist() if not components.empty else []
    bollards=_bollards(selected_port); bollard_ids=bollards.bollard_id.astype(str).tolist() if not bollards.empty else []
    if lines:
        a,b,c,d=st.columns(4)
        line=a.selectbox("Line",lines)
        winch=b.selectbox("Winch",["N/D"]+winches)
        fairlead=c.selectbox("Fairlead / Chock",["N/D"]+fairleads)
        bollard=d.selectbox("Shore bollard",["N/D"]+bollard_ids)
        if st.button("🔗 Save connection",type="primary"):
            if "N/D" in [winch,fairlead,bollard]: st.error("Seleziona Winch + Fairlead/Chock + Shore Bollard reali.")
            else:
                rope_d=None
                rr=inv[inv.line_id.astype(str)==line]
                if not rr.empty and pd.notna(rr.iloc[0].get("diameter_mm")): rope_d=float(rr.iloc[0].diameter_mm)
                upsert_connection(station,line,winch,fairlead,bollard,rope_d); st.session_state.mooring_selected_line=line; st.session_state.mooring_selected_component=None; st.rerun()
    else:
        st.info("Nessuna linea nell'inventario DB.")

    if not connections.empty:
        st.dataframe(connections[["line_id","winch_id","fairlead_id","bollard_id","centerline_angle_deg","geometry_status"]],use_container_width=True,hide_index=True)

    if selected_port:
        st.divider(); st.subheader("🗺️ 3D synchronized view"); _render_3d(station,selected_port)
