"""
views/tab_plans.py
Pianetti Mooring Station con posizionamento interattivo tramite click visivo.
"""

import io
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

from database.db_manager import (
    get_line_history,
    save_mooring_station_components,
    get_mooring_station_components,
)


def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio & Pianetti Interattivi")

    # Inizializzazione stazioni nel session_state
    if "mooring_stations" not in st.session_state or not st.session_state.mooring_stations:
        st.session_state.mooring_stations = {
            "Prua (Forward Station)": pd.DataFrame(
                columns=["comp_type", "comp_id", "pos_x", "pos_y", "assigned_line_id"]
            ),
            "Poppa (Aft Station)": pd.DataFrame(
                columns=["comp_type", "comp_id", "pos_x", "pos_y", "assigned_line_id"]
            ),
        }

    # 1. Selezione Stazione d'Ormeggio
    station_sel = st.selectbox(
        "Seleziona Stazione d'Ormeggio",
        list(st.session_state.mooring_stations.keys()),
    )
    if not station_sel:
        st.warning("Nessuna stazione trovata.")
        return

    # Recupero dati dal DB se il session_state della stazione è vuoto
    db_saved_comp = get_mooring_station_components(station_sel)
    if not db_saved_comp.empty and st.session_state.mooring_stations[station_sel].empty:
        formatted_df = pd.DataFrame({
            "comp_type": db_saved_comp["component_type"],
            "comp_id": db_saved_comp["component_id"],
            "pos_x": db_saved_comp["x_pos"],
            "pos_y": db_saved_comp["y_pos"],
            "assigned_line_id": db_saved_comp["line_id"]
        })
        st.session_state.mooring_stations[station_sel] = formatted_df

    st_df = st.session_state.mooring_stations[station_sel]
    lines_df = get_line_history()

    # 2. Upload dell'Immagine Pianetta
    uploaded_image = st.file_uploader(
        f"📷 Carica Pianetta (PNG/JPG) per: {station_sel}",
        type=["png", "jpg", "jpeg"],
        key=f"uploader_{station_sel}"
    )

    bg_img = None
    img_width, img_height = 800, 500
    if uploaded_image is not None:
        bg_img = Image.open(uploaded_image)
        img_width, img_height = bg_img.size

    # 3. Costruzione Grafico Interattivo Plotly
    fig = go.Figure()

    if bg_img is not None:
        fig.add_layout_image(
            dict(
                source=bg_img,
                xref="x",
                yref="y",
                x=0,
                y=img_height,
                sizex=img_width,
                sizey=img_height,
                sizing="stretch",
                opacity=0.85,
                layer="below"
            )
        )

    # Disegno dei punti salvati sulla pianetta
    if not st_df.empty:
        colors = {"WINCH": "#FF4B4B", "BASKET": "#FFA500", "CHOCK": "#00C853"}
        
        for c_type in st_df["comp_type"].unique():
            sub_df = st_df[st_df["comp_type"] == c_type]
            fig.add_trace(
                go.Scatter(
                    x=sub_df["pos_x"],
                    y=sub_df["pos_y"],
                    mode="markers+text",
                    marker=dict(size=20, color=colors.get(c_type, "#007BFF"), symbol="square"),
                    text=sub_df["comp_id"],
                    textposition="top center",
                    name=c_type,
                    customdata=sub_df["assigned_line_id"],
                    hovertemplate="<b>%{text}</b><br>Tipo: " + c_type + "<br>Cima: %{customdata}<extra></extra>"
                )
            )

    fig.update_xaxes(range=[0, img_width], showgrid=False, title="Coordinata X (px)")
    fig.update_yaxes(range=[0, img_height], showgrid=False, title="Coordinata Y (px)")
    fig.update_layout(
        title=f"Pianetta {station_sel} (Clicca sul punto desiderato dell'immagine)",
        height=550,
        margin=dict(l=20, r=20, t=40, b=20),
        clickmode="event+select"
    )

    st.markdown("---")
    col_chart, col_form = st.columns([2, 1])

    # Rilevamento Click sull'Immagine
    with col_chart:
        click_event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points")

        # Gestione download HTML
        buffer = io.StringIO()
        fig.write_html(buffer, include_plotlyjs="cdn")
        st.download_button(
            label="💾 Scarica Pianetto Mappato (HTML Interattivo)",
            data=buffer.getvalue().encode(),
            file_name=f"pianetto_{station_sel.replace(' ', '_')}.html",
            mime="text/html",
        )

    # Estrazione coordinate dal click
    clicked_x = 0.0
    clicked_y = 0.0
    if click_event and "selection" in click_event and "points" in click_event["selection"]:
        pts = click_event["selection"]["points"]
        if len(pts) > 0:
            clicked_x = float(pts[0].get("x", 0.0))
            clicked_y = float(pts[0].get("y", 0.0))

    # Form per assegnare parametri al punto cliccato
    with col_form:
        st.subheader("🎯 Aggiungi / Assegna Componente")
        st.info(f"Coordinata Selezionata: **X={clicked_x:.1f}, Y={clicked_y:.1f}**")

        comp_type = st.selectbox("Tipologia Elemento", ["WINCH", "BASKET", "CHOCK"])
        comp_id = st.text_input("Identificativo (es. W1, B2, C1)", f"{comp_type[0]}_{len(st_df)+1}")

        # La cima si assegna solo a WINCH e BASKET
        line_options = ["Nessuna"]
        if not lines_df.empty and "line_id" in lines_df.columns:
            line_options += lines_df["line_id"].tolist()

        if comp_type in ["WINCH", "BASKET"]:
            assigned_line = st.selectbox("Cima d'Ormeggio Associata", line_options)
        else:
            assigned_line = "N/D"
            st.caption("ℹ️ Ai CHOCK (Passacavi) non viene associata direttamente una cima.")

        if st.button("➕ Salva Elemento sul Pianetto", use_container_width=True):
            new_row = pd.DataFrame([{
                "comp_type": comp_type,
                "comp_id": comp_id,
                "pos_x": clicked_x if clicked_x != 0.0 else img_width / 2,
                "pos_y": clicked_y if clicked_y != 0.0 else img_height / 2,
                "assigned_line_id": assigned_line
            }])
            st_df = pd.concat([st_df, new_row], ignore_index=True)
            st.session_state.mooring_stations[station_sel] = st_df

            # Salvataggio immediato nel DB SQLite
            db_components = [
                {
                    "id": row["comp_id"],
                    "type": row["comp_type"],
                    "x": row["pos_x"],
                    "y": row["pos_y"],
                    "line_id": row["assigned_line_id"]
                }
                for _, row in st_df.iterrows()
            ]
            save_mooring_station_components(db_components, station_sel)
            st.success(f"Elemento {comp_id} aggiunto con successo!")
            st.rerun()

    # Tabella modifica/eliminazione componenti
    st.markdown("---")
    st.subheader(f"⚙️ Gestione Componenti Posizionati: {station_sel}")
    edited_df = st.data_editor(
        st_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{station_sel}"
    )
    
    if st.button("💾 Aggiorna Modifiche Tabellari su DB"):
        st.session_state.mooring_stations[station_sel] = edited_df
        db_components = [
            {
                "id": str(row.get("comp_id", "")),
                "type": str(row.get("comp_type", "WINCH")),
                "x": float(row.get("pos_x", 0.0)),
                "y": float(row.get("pos_y", 0.0)),
                "line_id": str(row.get("assigned_line_id", "N/D"))
            }
            for _, row in edited_df.iterrows()
        ]
        save_mooring_station_components(db_components, station_sel)
        st.success("Database aggiornato con le ultime modifiche!")
        st.rerun()
