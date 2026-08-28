"""
views/tab_plans.py
Pianetti Mooring Station con singola immagine dinamica (click + rendering marcatori unificato).
"""

import io
import os
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates

from database.db_manager import (
    get_line_history,
    save_mooring_station_components,
    get_mooring_station_components,
    save_station_image_file,
    get_station_image_path,
)


def draw_components_on_image(image: Image.Image, components_df: pd.DataFrame) -> Image.Image:
    """Disegna i marcatori dei componenti direttamente sull'immagine Pillow."""
    img_copy = image.copy().convert("RGB")
    draw = ImageDraw.Draw(img_copy)

    # Palette colori componenti
    color_map = {
        "WINCH": (255, 75, 75),      # Rosso
        "BASKET": (255, 165, 0),    # Arancione
        "CHOCK": (0, 200, 83)       # Verde
    }

    marker_size = 10  # Raggio del marcatore in px

    for _, row in components_df.iterrows():
        x = float(row.get("pos_x", 0))
        y = float(row.get("pos_y", 0))
        c_type = str(row.get("comp_type", "WINCH"))
        c_id = str(row.get("comp_id", ""))

        color = color_map.get(c_type, (0, 123, 255))

        # Disegna Quadrato Marcatore
        draw.rectangle(
            [x - marker_size, y - marker_size, x + marker_size, y + marker_size],
            fill=color,
            outline=(255, 255, 255),
            width=2
        )

        # Disegna Etichetta ID
        draw.text((x - 8, y - marker_size - 12), c_id, fill=(0, 0, 0))

    return img_copy


def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio & Pianetti Interattivi")

    # Inizializzazione stazioni
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

    # 2. Gestione e Ridimensionamento Immagine Persistente
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

    if saved_img_path and os.path.exists(saved_img_path):
        raw_img = Image.open(saved_img_path)
    else:
        raw_img = Image.new('RGB', (600, 350), color=(230, 230, 230))

    # ridimensionamento mantenendo le proporzioni corrette
    TARGET_WIDTH = 600
    w_percent = TARGET_WIDTH / float(raw_img.size[0])
    target_height = int(float(raw_img.size[1]) * float(w_percent))
    bg_img = raw_img.resize((TARGET_WIDTH, target_height), Image.Resampling.LANCZOS)

    # Chiave sessione per il click corrente
    key_click = f"click_pos_{station_sel}"
    if key_click not in st.session_state:
        st.session_state[key_click] = {"x": int(TARGET_WIDTH / 2), "y": int(target_height / 2)}

    # Disegna i componenti già salvati sull'immagine ridimensionata
    annotated_img = draw_components_on_image(bg_img, st_df)

    st.markdown("---")
    col_map, col_form = st.columns([1.8, 1])

    # 3. UNICA IMMAGINE INTERATTIVA
    with col_map:
        st.subheader("👆 Clicca per Posizionare / Droppare")
        
        # Componente a Click Diretto
        value = streamlit_image_coordinates(
            annotated_img,
            width=TARGET_WIDTH,
            key=f"img_coords_{station_sel}"
        )

        if value is not None:
            st.session_state[key_click] = {"x": value["x"], "y": value["y"]}

    # 4. FORM DI AGGIUNTA
    with col_form:
        st.subheader("🎯 Aggiungi Componente")
        
        curr_x = st.session_state[key_click]["x"]
        curr_y = st.session_state[key_click]["y"]
        
        st.info(f"Punto Selezionato: **X={curr_x} px, Y={curr_y} px**")

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
            st.success(f"Elemento {comp_id} aggiunto!")
            st.rerun()

    # 5. TABELLA GESTIONE
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
        st.success("Database aggiornato!")
        st.rerun()
