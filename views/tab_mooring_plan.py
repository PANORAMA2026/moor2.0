"""
views/tab_mooring_plan.py
Interactive mooring station plan + synchronized 3D geometry.

This first implementation deliberately separates:
- reference drawing (uploaded station plan),
- engineering components (persistent DB),
- line connectivity (persistent DB),
- calculation geometry (derived automatically).

No engineering coordinate is invented from the drawing. Components can be placed
on the plan and their ship X/Y/Z coordinates entered only when known/calibrated.
"""

import os
import math

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
from streamlit_image_coordinates import streamlit_image_coordinates

from database.db_manager import (
    get_station_image_path,
    save_station_image_file,
    load_lines_inventory_from_db,
    load_certificates_from_db,
)
from core.mooring_geometry import (
    COMPONENT_TYPES,
    init_mooring_geometry_db,
    get_components,
    get_connections,
    get_line_detail,
    upsert_component,
    delete_component,
    upsert_connection,
    recalculate_all,
)
from config.constants import DB_FILE_PATH


STATIONS = [
    "Prua (Forward Station)",
    "Poppa (Aft Station)",
]


def _nearest_component(components: pd.DataFrame, x: float, y: float, threshold_px: float = 35):
    if components.empty:
        return None
    best = None
    best_d = threshold_px
    for _, r in components.iterrows():
        if pd.isna(r.get("plan_x_px")) or pd.isna(r.get("plan_y_px")):
            continue
        d = math.hypot(float(r["plan_x_px"]) - x, float(r["plan_y_px"]) - y)
        if d < best_d:
            best = str(r["component_id"])
            best_d = d
    return best


def _nearest_line(components: pd.DataFrame, connections: pd.DataFrame, x: float, y: float):
    """Find the closest displayed Winch->Fairlead segment."""
    if components.empty or connections.empty:
        return None
    lookup = {str(r.component_id): r for r in components.itertuples()}
    best_id = None
    best_d = 18.0

    def seg_distance(px, py, ax, ay, bx, by):
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        den = vx * vx + vy * vy
        t = 0.0 if den == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / den))
        qx, qy = ax + t * vx, ay + t * vy
        return math.hypot(px - qx, py - qy)

    for r in connections.itertuples():
        w = lookup.get(str(r.winch_id))
        f = lookup.get(str(r.fairlead_id))
        if not w or not f:
            continue
        if any(pd.isna(getattr(v, "plan_x_px", None)) or pd.isna(getattr(v, "plan_y_px", None)) for v in (w, f)):
            continue
        d = seg_distance(x, y, float(w.plan_x_px), float(w.plan_y_px), float(f.plan_x_px), float(f.plan_y_px))
        if d < best_d:
            best_d = d
            best_id = str(r.line_id)
    return best_id


def _draw_plan(station_name: str, image: Image.Image, components: pd.DataFrame,
               connections: pd.DataFrame, selected_component=None, selected_line=None):
    canvas = image.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)

    # Engineering overlays: lines are intentionally drawn only where both ship-side
    # endpoints exist. Shore bollards are outside the station plan and are handled in 3D.
    lookup = {str(r.component_id): r for r in components.itertuples()}
    for r in connections.itertuples():
        w = lookup.get(str(r.winch_id))
        f = lookup.get(str(r.fairlead_id))
        if not w or not f:
            continue
        if any(pd.isna(getattr(v, "plan_x_px", None)) or pd.isna(getattr(v, "plan_y_px", None)) for v in (w, f)):
            continue
        pts = [(int(w.plan_x_px), int(w.plan_y_px)), (int(f.plan_x_px), int(f.plan_y_px))]
        width = 6 if str(r.line_id) == str(selected_line) else 3
        draw.line(pts, fill=(255, 60, 60) if str(r.line_id) == str(selected_line) else (30, 120, 220), width=width)
        mx = int((pts[0][0] + pts[1][0]) / 2)
        my = int((pts[0][1] + pts[1][1]) / 2)
        draw.text((mx + 4, my + 4), str(r.line_id), fill=(220, 30, 30))

    for r in components.itertuples():
        if pd.isna(r.plan_x_px) or pd.isna(r.plan_y_px):
            continue
        x, y = int(r.plan_x_px), int(r.plan_y_px)
        radius = 9 if str(r.component_id) == str(selected_component) else 6
        outline = (255, 60, 60) if str(r.component_id) == str(selected_component) else (20, 20, 20)
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline=outline, width=3)
        draw.text((x + 10, y - 10), str(r.component_id), fill=(20, 20, 20))

    return canvas


def _port_bollards(port_name: str):
    """Read only real rows from port_bollards; never use the legacy fallback defaults."""
    import sqlite3
    conn = sqlite3.connect(DB_FILE_PATH)
    df = pd.read_sql_query(
        "SELECT bollard_id, x_m, y_m, z_m, swl_t, stato FROM port_bollards WHERE port_name = ?",
        conn, params=(port_name,))
    conn.close()
    return df


def _render_3d(station_name: str, selected_port: str):
    try:
        import plotly.graph_objects as go
    except Exception as exc:
        st.error(f"3D non disponibile: {exc}")
        return

    components = get_components(station_name)
    connections = get_connections(station_name)
    bollards = _port_bollards(selected_port)

    fig = go.Figure()

    if not components.empty:
        valid = components.dropna(subset=["x_m", "y_m", "z_m"])
        if not valid.empty:
            fig.add_trace(go.Scatter3d(
                x=valid["x_m"], y=valid["y_m"], z=valid["z_m"],
                mode="markers+text",
                text=valid["component_id"],
                textposition="top center",
                marker=dict(size=6),
                name="Ship components",
                customdata=valid["component_id"],
                hovertemplate="%{text}<br>X=%{x:.2f} m<br>Y=%{y:.2f} m<br>Z=%{z:.2f} m<extra></extra>",
            ))

    comp_lookup = {str(r.component_id): r for r in components.itertuples()}
    bollard_lookup = {str(r.bollard_id): r for r in bollards.itertuples()}
    for r in connections.itertuples():
        w = comp_lookup.get(str(r.winch_id))
        f = comp_lookup.get(str(r.fairlead_id))
        b = bollard_lookup.get(str(r.bollard_id))
        if not w or not f or not b:
            continue
        vals = [w.x_m, f.x_m, b.x_m, w.y_m, f.y_m, b.y_m, w.z_m, f.z_m, b.z_m]
        if any(pd.isna(v) for v in vals):
            continue
        fig.add_trace(go.Scatter3d(
            x=[w.x_m, f.x_m, b.x_m],
            y=[w.y_m, f.y_m, b.y_m],
            z=[w.z_m, f.z_m, b.z_m],
            mode="lines+markers",
            name=f"Line {r.line_id}",
            line=dict(width=6),
            hovertemplate=f"Line {r.line_id}<extra></extra>",
        ))

    fig.update_layout(
        height=650,
        margin=dict(l=0, r=0, t=40, b=0),
        scene=dict(
            xaxis_title="Ship X (m)",
            yaxis_title="Ship Y (m)",
            zaxis_title="Ship Z (m)",
            aspectmode="data",
        ),
        title=f"3D Mooring Geometry — {station_name}",
        showlegend=True,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_tab_mooring_plan(selected_port=None):
    init_mooring_geometry_db()
    st.header("🏗️ Interactive Mooring Station Plan")
    st.caption("2D plan e 3D geometry condividono gli stessi componenti e collegamenti salvati nel DB.")

    station = st.selectbox("Stazione", STATIONS, key="interactive_station")
    image_path = get_station_image_path(station)

    upload = st.file_uploader(
        "Carica il pianetto reale della stazione (PNG/JPG)",
        type=["png", "jpg", "jpeg"],
        key=f"interactive_plan_upload_{station}",
    )
    if upload is not None:
        _, ext = os.path.splitext(upload.name)
        image_path = save_station_image_file(station, upload.getvalue(), ext or ".png")
        st.success("Pianetto salvato. Ora può essere usato come riferimento permanente della stazione.")
        st.rerun()

    if not image_path or not os.path.exists(image_path):
        st.info("Per questa stazione non è ancora presente un pianetto nel DB. Carica il file reale sopra.")
        return

    image = Image.open(image_path)
    components = get_components(station)
    connections = get_connections(station)

    if "selected_component" not in st.session_state:
        st.session_state.selected_component = None
    if "selected_line" not in st.session_state:
        st.session_state.selected_line = None

    edit_mode = st.toggle("✏️ Edit mode", value=False, help="In edit mode un click sul pianetto può creare un componente nel punto selezionato.")

    left, right = st.columns([2.2, 1])
    with left:
        canvas = _draw_plan(
            station, image, components, connections,
            st.session_state.selected_component, st.session_state.selected_line,
        )
        click = streamlit_image_coordinates(canvas, key=f"plan_canvas_{station}")

        if click:
            x, y = float(click["x"]), float(click["y"])
            line_id = _nearest_line(components, connections, x, y)
            comp_id = _nearest_component(components, x, y)
            if line_id:
                st.session_state.selected_line = line_id
                st.session_state.selected_component = None
            elif comp_id:
                st.session_state.selected_component = comp_id
                st.session_state.selected_line = None
            elif edit_mode:
                st.session_state.pending_plan_x = x
                st.session_state.pending_plan_y = y
                st.info(f"Punto selezionato: ({x:.0f}, {y:.0f}) px. Compila il pannello a destra e salva.")

    with right:
        st.subheader("Engineering data")
        if st.session_state.selected_line:
            detail = get_line_detail(station, st.session_state.selected_line)
            st.markdown(f"### Line {st.session_state.selected_line}")
            st.write(f"**Winch:** {detail.get('Winch', 'N/D')}")
            st.write(f"**Fairlead:** {detail.get('Fairlead', 'N/D')}")
            st.write(f"**Bollard:** {detail.get('Bollard', 'N/D')}")
            angle = detail.get("contact_angle_deg")
            st.metric("Centerline direction change", "N/D" if pd.isna(angle) or angle is None else f"{float(angle):.1f}°")
            st.caption("Questo angolo è la variazione di direzione tra i due tratti. Non è ancora il contact/wrap angle della fairlead.")
            if detail.get("geometry_status") == "CENTERLINE_ANGLE_ONLY":
                st.warning("Diametro fairlead / geometria di contatto non ancora disponibile: nessuna correzione di attrito o wrap applicata.")

            inv = load_lines_inventory_from_db()
            certs = load_certificates_from_db()
            if not inv.empty and str(st.session_state.selected_line) in inv["line_id"].astype(str).values:
                lr = inv[inv["line_id"].astype(str) == str(st.session_state.selected_line)].iloc[0]
                st.write(f"**Line type:** {lr.get('line_type', 'N/D')}")
                st.write(f"**MBL:** {lr.get('mbl_tons', 'N/D')} t")
                st.write(f"**Certificate:** {lr.get('cert_id', 'N/D')}")
                st.write(f"**Diameter:** {lr.get('diameter_mm', 'N/D')} mm")
                if not certs.empty and str(lr.get('cert_id')) in certs["cert_id"].astype(str).values:
                    cr = certs[certs["cert_id"].astype(str) == str(lr.get('cert_id'))].iloc[0]
                    st.write(f"**Manufacturer:** {cr.get('manufacturer', 'N/D')}")

        elif st.session_state.selected_component:
            cid = st.session_state.selected_component
            row = components[components["component_id"].astype(str) == str(cid)]
            if not row.empty:
                r = row.iloc[0]
                st.markdown(f"### {cid}")
                st.write(f"**Type:** {r.get('component_type', 'N/D')}")
                st.write(f"**Plan:** ({r.get('plan_x_px', 'N/D')}, {r.get('plan_y_px', 'N/D')}) px")
                st.write(f"**XYZ:** ({r.get('x_m', 'N/D')}, {r.get('y_m', 'N/D')}, {r.get('z_m', 'N/D')}) m")
                st.write(f"**Diameter:** {r.get('diameter_mm', 'N/D')} mm")

        st.markdown("---")
        st.subheader("Add / edit component")
        pending_x = st.session_state.get("pending_plan_x")
        pending_y = st.session_state.get("pending_plan_y")
        default_id = st.session_state.selected_component or ""
        comp_id = st.text_input("Component ID", value=default_id, key=f"comp_id_{station}")
        comp_type = st.selectbox("Component type", COMPONENT_TYPES, key=f"comp_type_{station}")
        c1, c2 = st.columns(2)
        with c1:
            x_m = st.number_input("Ship X (m)", value=0.0, format="%.3f", key=f"x_m_{station}")
            plan_x = st.number_input("Plan X (px)", value=float(pending_x or 0.0), format="%.1f", key=f"plan_x_{station}")
            z_m = st.number_input("Ship Z (m)", value=0.0, format="%.3f", key=f"z_m_{station}")
        with c2:
            y_m = st.number_input("Ship Y (m)", value=0.0, format="%.3f", key=f"y_m_{station}")
            plan_y = st.number_input("Plan Y (px)", value=float(pending_y or 0.0), format="%.1f", key=f"plan_y_{station}")
            diameter = st.number_input("Diameter (mm)", value=0.0, min_value=0.0, format="%.1f", key=f"diam_{station}")

        if st.button("💾 Save component", key=f"save_comp_{station}", use_container_width=True):
            if not comp_id.strip():
                st.error("Component ID obbligatorio.")
            else:
                upsert_component(station, comp_id.strip(), comp_type, plan_x, plan_y, x_m, y_m, z_m, diameter)
                st.session_state.pending_plan_x = None
                st.session_state.pending_plan_y = None
                st.session_state.selected_component = comp_id.strip()
                st.session_state.selected_line = None
                st.rerun()

        if st.session_state.selected_component and st.button("🗑️ Delete component", key=f"delete_comp_{station}"):
            delete_component(station, st.session_state.selected_component)
            st.session_state.selected_component = None
            st.rerun()

    st.markdown("---")
    st.subheader("🔗 Mooring line connectivity")
    inv = load_lines_inventory_from_db()
    line_ids = inv["line_id"].astype(str).tolist() if not inv.empty and "line_id" in inv.columns else []
    component_ids = components["component_id"].astype(str).tolist() if not components.empty else []
    winches = components[components["component_type"] == "WINCH"]["component_id"].astype(str).tolist() if not components.empty else []
    fairleads = components[components["component_type"].isin(["FAIRLEAD", "CHOCK", "CAPSTAN"])]["component_id"].astype(str).tolist() if not components.empty else []

    if not line_ids:
        st.info("Nessuna cima presente nell'inventario DB. Inserisci prima le linee/certificati reali.")
    else:
        a, b, c, d = st.columns(4)
        line_id = a.selectbox("Line", line_ids, key=f"conn_line_{station}")
        winch = b.selectbox("Winch", ["N/D"] + winches, key=f"conn_winch_{station}")
        fairlead = c.selectbox("Fairlead / Chock", ["N/D"] + fairleads, key=f"conn_fairlead_{station}")
        bollards = _port_bollards(selected_port or "")
        bollard_ids = bollards["bollard_id"].astype(str).tolist() if not bollards.empty else []
        bollard = d.selectbox("Shore bollard", ["N/D"] + bollard_ids, key=f"conn_bollard_{station}")

        rope_d = None
        if not inv.empty and line_id in inv["line_id"].astype(str).values:
            rr = inv[inv["line_id"].astype(str) == line_id].iloc[0]
            if pd.notna(rr.get("diameter_mm")):
                rope_d = float(rr.get("diameter_mm"))

        if st.button("🔗 Save connection", type="primary", key=f"save_conn_{station}"):
            if winch == "N/D" or fairlead == "N/D" or bollard == "N/D":
                st.error("Per ora il collegamento richiede Winch + Fairlead/Chock + Shore bollard.")
            else:
                upsert_connection(station, line_id, winch, fairlead, bollard, rope_d)
                st.session_state.selected_line = line_id
                st.session_state.selected_component = None
                st.success(f"Line {line_id}: {winch} → {fairlead} → {bollard} salvata.")
                st.rerun()

    if not connections.empty:
        st.dataframe(
            connections[["line_id", "winch_id", "fairlead_id", "bollard_id", "contact_angle_deg", "geometry_status"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("---")
    st.subheader("🗺️ 3D synchronized view")
    if selected_port:
        _render_3d(station, selected_port)
    else:
        st.info("Seleziona un porto dalla sidebar per completare la vista 3D verso le bitte.")

    st.caption("Nota tecnica: la geometria della fairlead sarà raffinata dopo l'inserimento dei diametri reali. Il software non applica automaticamente coefficienti di attrito o capstan equation senza dati che li giustifichino.")
