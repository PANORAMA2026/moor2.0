"""
views/tab_plans.py
Pianetti Mooring Station con posizionamento interattivo tramite click, 
tracciamento in tempo reale delle coordinate ed eliminazione elementi.
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

    # Sincronizzazione con DB se la sessione corrente è vuota
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

    # TRACCIA INVISIBILE: Fondamentale per forzare Plotly a mostrare le coordinate del cursore ovunque
    fig.add_trace(
        go.Scatter(
            x=[0, img_width, img_width, 0, 0],
            y=[0, 0, img_height, img_height, 0],
            fill="toself",
            fillcolor="rgba(255,255,255,0)",  # Trasparente
            line=dict(color="rgba(255,255,255,0)"),
            hoverinfo="x+y",
            name="Sfondo Pianetta",
            showlegend=False,
            mode="lines"
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
                    marker=dict(size=22, color=colors.get(c_type, "#007BFF"), symbol="square", line=dict(color="white", width=2)),
                    text=sub_df["comp_id"],
                    textposition="top center",
                    name=c_type,
                    customdata=sub_df["assigned_line_id"],
                    hovertemplate="<b>%{text}</b><br>Tipo: " + c_type + "<br>Cima: %{customdata}<extra></extra>"
                )
            )

    # Impostazione assi con SPIKES (mirino a croce che segue il cursore)
    fig.update_xaxes(
        range=[0, img_width], showgrid=False, title="Coordinata X (px)",
        showspikes=True, spikemode="across", spikesnap="cursor", spikecolor="gray", spikethickness=1
    )
    fig.update_yaxes(
        range=[0, img_height], showgrid=False, title="Coordinata Y (px)",
        showspikes=True, spikemode="across", spikesnap="cursor", spikecolor="gray", spikethickness=1
    )
    fig.update_layout(
        title=f"Pianetta {station_sel} (Hover per Coordinate, Click per Azioni)",
        height=550,
        margin=dict(l=20, r=20, t=40, b=20),
        clickmode="event+select",
        hovermode="closest"
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

    # Estrazione coordinate e identificazione dell'elemento cliccato
    clicked_x, clicked_y = 0.0, 0.0
    selected_comp_id = None

    if click_event and "selection" in click_event and "points" in click_event["selection"]:
        pts = click_event["selection"]["points"]
        if len(pts) > 0:
            pt = pts[0]
            clicked_x = float(pt.get("x", 0.0))
            clicked_y = float(pt.get("y", 0.0))
            # Se la traccia cliccata ha un testo (quindi è un marker generato da noi e non il livello di sfondo)
            if "text" in pt and pt["text"]:
                selected_comp_id = pt["text"]

    # Pannello Laterale: Aggiunta o Eliminazione a seconda del click
    with col_form:
        if selected_comp_id:
            # 🔴 MODALITÀ ELIMINAZIONE (Elemento Esistente Selezionato)
            st.error("🗑️ Elimina Elemento")
            st.warning(f"Hai selezionato il componente: **{selected_comp_id}**")
            
            if st.button(f"Conferma Eliminazione {selected_comp_id}", use_container_width=True, type="primary"):
                # Rimuovi l'elemento dal dataframe
                st_df = st_df[st_df["comp_id"] != selected_comp_id]
                st.session_state.mooring_stations[station_sel] = st_df
                
                # Salva il nuovo stato (senza l'elemento) nel database
                db_components = [
                    {"id": row["comp_id"], "type": row["comp_type"], "x": row["pos_x"], "y": row["pos_y"], "line_id": row["assigned_line_id"]}
                    for _, row in st_df.iterrows()
                ]
                save_mooring_station_components(db_components, station_sel)
                st.rerun()
                
        else:
            # 🟢 MODALITÀ AGGIUNTA (Spazio Vuoto Selezionato)
            st.subheader("🎯 Aggiungi Componente")
            st.info(f"Coordinata Click: **X={clicked_x:.1f}, Y={clicked_y:.1f}**")

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
                    {"id": row["comp_id"], "type": row["comp_type"], "x": row["pos_x"], "y": row["pos_y"], "line_id": row["assigned_line_id"]}
                    for _, row in st_df.iterrows()
                ]
                save_mooring_station_components(db_components, station_sel)
                st.success(f"Elemento {comp_id} aggiunto con successo!")
                st.rerun()

    # Tabella riepilogativa (può essere usata anche per modifiche rapide di massa)
    st.markdown("---")
    st.subheader(f"⚙️ Gestione Tabellare Componenti: {station_sel}")
    edited_df = st.data_editor(
        st_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"editor_{station_sel}"
    )
    
    if st.button("💾 Sincronizza Tabella su DB"):
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
        st.success("Database aggiornato con successo!")
        st.rerun()
