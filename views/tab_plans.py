"""
views/tab_plans.py
Pianetti Mooring Station con posizionamento istantaneo tramite Click Diretto sull'immagine.
"""

import io
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image
from streamlit_image_coordinates import streamlit_image_coordinates

from database.db_manager import (
    get_line_history,
    save_mooring_station_components,
    get_mooring_station_components,
    save_station_image_file,
    get_station_image_path,
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

    # Sincronizzazione automatica dal DB
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

    # 2. Gestione Immagine
    saved_img_path = get_station_image_path(station_sel)

    uploaded_image = st.file_uploader(
        f"📷 Carica/Sostituisci Pianetta per: {station_sel}",
        type=["png", "jpg", "jpeg"],
        key=f"uploader_{station_sel}"
    )

    if uploaded_image is not None:
        file_bytes = uploaded_image.getvalue()
        _, ext = os.path.splitext(uploaded_image.name)
        saved_img_path = save_station_image_file(station_sel, file_bytes, ext)
        st.success("Immagine pianetta salvata permanentemente!")

    # Caricamento o creazione immagine vuota di fallback
    if saved_img_path and os.path.exists(saved_img_path):
        bg_img = Image.open(saved_img_path)
    else:
        bg_img = Image.new('RGB', (800, 500), color=(220, 220, 220))

    img_width, img_height = bg_img.size

    # Stato coordinate per il click
    key_click = f"click_pos_{station_sel}"
    if key_click not in st.session_state:
        st.session_state[key_click] = {"x": int(img_width / 2), "y": int(img_height / 2)}

    st.markdown("---")
    col_map, col_form = st.columns([2, 1])

    # 3. INTERFACCIA A CLICK DIRETTO SULL'IMMAGINE
    with col_map:
        st.subheader("👆 Clicca sull'immagine per posizionare")
        
        # Componente a click istantaneo
        value = streamlit_image_coordinates(
            bg_img,
            key=f"img_coords_{station_sel}"
        )

        if value is not None:
            st.session_state[key_click] = {"x": value["x"], "y": value["y"]}

    # 4. FORM DI AGGIUNTA RAPIDA
    with col_form:
        st.subheader("🎯 Aggiungi Componente")
        
        curr_x = st.session_state[key_click]["x"]
        curr_y = st.session_state[key_click]["y"]
        
        st.success(f"Punto Selezionato: **X={curr_x} px, Y={curr_y} px**")

        comp_type = st.selectbox("Tipologia Elemento", ["WINCH", "BASKET", "CHOCK"])
        comp_id = st.text_input("Identificativo (es. W1, B2, C1)", f"{comp_type[0]}_{len(st_df)+1}")

        line_options = ["Nessuna"]
        if not lines_df.empty and "line_id" in lines_df.columns:
            line_options += lines_df["line_id"].tolist()

        if comp_type in ["WINCH", "BASKET"]:
            assigned_line = st.selectbox("Cima d'Ormeggio Associata", line_options)
        else:
            assigned_line = "N/D"

        if st.button("➕ Droppa Elemento Qui", use_container_width=True, type="primary"):
            new_row = pd.DataFrame([{
                "comp_type": comp_type,
                "comp_id": comp_id,
                "pos_x": curr_x,
                "pos_y": curr_y,
                "assigned_line_id": assigned_line
            }])
            st_df = pd.concat([st_df, new_row], ignore_index=True)
            st.session_state.mooring_stations[station_sel] = st_df

            db_components = [
                {"id": row["comp_id"], "type": row["comp_type"], "x": row["pos_x"], "y": row["pos_y"], "line_id": row["assigned_line_id"]}
                for _, row in st_df.iterrows()
            ]
            save_mooring_station_components(db_components, station_sel)
            st.success(f"Elemento {comp_id} piazzato!")
            st.rerun()

    # 5. VISUALIZZAZIONE COMPLETA CON GLI ELEMENTI SALVATI (PLOTLY)
    st.markdown("---")
    st.subheader("📊 Mappa Completa Pianetto Mappato")

    fig = go.Figure()

    fig.add_layout_image(
        dict(
            source=bg_img,
            xref="x", yref="y",
            x=0, y=img_height,
            sizex=img_width, sizey=img_height,
            sizing="stretch", opacity=0.85, layer="below"
        )
    )

    if not st_df.empty:
        colors = {"WINCH": "#FF4B4B", "BASKET": "#FFA500", "CHOCK": "#00C853"}
        for c_type in st_df["comp_type"].unique():
            sub_df = st_df[st_df["comp_type"] == c_type]
            # Nota: Conversione coordinata Y per Plotly Top-Down
            fig.add_trace(
                go.Scatter(
                    x=sub_df["pos_x"],
                    y=img_height - sub_df["pos_y"],
                    mode="markers+text",
                    marker=dict(size=22, color=colors.get(c_type, "#007BFF"), symbol="square", line=dict(color="white", width=2)),
                    text=sub_df["comp_id"],
                    textposition="top center",
                    name=c_type,
                    customdata=sub_df["assigned_line_id"],
                    hovertemplate="<b>%{text}</b><br>Tipo: " + c_type + "<br>Cima: %{customdata}<extra></extra>"
                )
            )

    fig.update_xaxes(range=[0, img_width], showgrid=False, visible=False)
    fig.update_yaxes(range=[0, img_height], showgrid=False, visible=False)
    fig.update_layout(height=450, margin=dict(l=10, r=10, t=10, b=10))

    st.plotly_chart(fig, use_container_width=True)

    # Tabella Modifica/Eliminazione
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
