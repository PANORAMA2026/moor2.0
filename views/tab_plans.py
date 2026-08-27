"""
views/tab_plans.py
Pianetti Mooring Station, caricamento planimetrie visuali, 
esportazione HTML e lavagna interattiva per annotazioni MSO.
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

try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS = True
except ImportError:
    HAS_CANVAS = False


def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio, Pianetti & Annotazione")

    # Inizializzazione stazioni predefinite se non presenti nel session_state
    if "mooring_stations" not in st.session_state or not st.session_state.mooring_stations:
        st.session_state.mooring_stations = {
            "Prua (Forward Station)": pd.DataFrame(
                columns=["winch_id", "chock_id", "chock_x_m", "chock_y_m", "assigned_line_id"]
            ),
            "Poppa (Aft Station)": pd.DataFrame(
                columns=["winch_id", "chock_id", "chock_x_m", "chock_y_m", "assigned_line_id"]
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

    # Sincronizzazione automatica con il DB al primo caricamento della stazione
    db_saved_comp = get_mooring_station_components(station_sel)
    if not db_saved_comp.empty and st.session_state.mooring_stations[station_sel].empty:
        formatted_df = pd.DataFrame({
            "winch_id": db_saved_comp["component_id"],
            "chock_id": db_saved_comp["component_id"].apply(lambda val: f"C_{val}"),
            "chock_x_m": db_saved_comp["x_pos"],
            "chock_y_m": db_saved_comp["y_pos"],
            "assigned_line_id": db_saved_comp["line_id"]
        })
        st.session_state.mooring_stations[station_sel] = formatted_df

    st_df = st.session_state.mooring_stations[station_sel]
    lines_df = get_line_history()

    # 2. Upload dell'Immagine di Sfondo della Pianetta
    uploaded_image = st.file_uploader(
        f"📷 Carica Immagine Pianetta / Planimetria per: {station_sel}",
        type=["png", "jpg", "jpeg"],
        key=f"uploader_{station_sel}"
    )

    bg_img = None
    if uploaded_image is not None:
        bg_img = Image.open(uploaded_image)

    # 3. Form Inserimento/Posizionamento Punti (Winch, Basket, Passacavo)
    st.markdown("---")
    col_input, col_table = st.columns([1, 2])

    with col_input:
        st.subheader("🛠️ Aggiungi Componente Pianetta")
        comp_type = st.selectbox("Tipologia Elemento", ["WINCH", "BASKET (Cesto)", "CHOCK (Passacavo)"])
        winch_id = st.text_input("Identificativo Winch / Cesto", f"W_{len(st_df)+1}")
        chock_id = st.text_input("Identificativo Passacavo (Chock)", f"C_{len(st_df)+1}")
        
        pos_x = st.slider("Coordinata X / Longitudinale", 0.0, 100.0, 50.0, step=0.5)
        pos_y = st.slider("Coordinata Y / Trasversale", 0.0, 100.0, 50.0, step=0.5)

        line_options = ["Nessuna"]
        if not lines_df.empty and "line_id" in lines_df.columns:
            line_options += lines_df["line_id"].tolist()
        
        assigned_line = st.selectbox("Cima d'Ormeggio Associata", line_options)

        if st.button("➕ Posiziona sulla Pianetta", use_container_width=True):
            new_row = pd.DataFrame([{
                "winch_id": f"{comp_type[:1]}_{winch_id}",
                "chock_id": chock_id,
                "chock_x_m": pos_x,
                "chock_y_m": pos_y,
                "assigned_line_id": assigned_line if assigned_line != "Nessuna" else "N/D"
            }])
            st_df = pd.concat([st_df, new_row], ignore_index=True)
            st.session_state.mooring_stations[station_sel] = st_df

            # Persistence automatica su SQLite DB
            db_components = [
                {
                    "id": row["winch_id"],
                    "type": comp_type,
                    "x": row["chock_x_m"],
                    "y": row["chock_y_m"],
                    "line_id": row["assigned_line_id"]
                }
                for _, row in st_df.iterrows()
            ]
            save_mooring_station_components(db_components, station_sel)
            st.success("Componente posizionato e salvato a DB!")
            st.rerun()

    with col_table:
        st.subheader(f"⚙️ Configurazione Tabellare: {station_sel}")
        edited_st = st.data_editor(
            st_df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"edit_st_{station_sel}",
        )
        st.session_state.mooring_stations[station_sel] = edited_st

        if st.button("💾 Salva Modifiche Tabelle su DB", key=f"save_tbl_{station_sel}"):
            db_components = [
                {
                    "id": str(row.get("winch_id", "")),
                    "type": "COMPONENT",
                    "x": float(row.get("chock_x_m", 0.0)),
                    "y": float(row.get("chock_y_m", 0.0)),
                    "line_id": str(row.get("assigned_line_id", "N/D"))
                }
                for _, row in edited_st.iterrows()
            ]
            save_mooring_station_components(db_components, station_sel)
            st.success("Pianetto aggiornato e registrato nel DB!")

    # 4. Rendering Grafico Plotly (con Sfondo Immagine Pianetta se presente)
    fig_st = go.Figure()

    if bg_img is not None:
        fig_st.add_layout_image(
            dict(
                source=bg_img,
                xref="x",
                yref="y",
                x=0,
                y=100,
                sizex=100,
                sizey=100,
                sizing="stretch",
                opacity=0.8,
                layer="below"
            )
        )

    if not edited_st.empty:
        fig_st.add_trace(
            go.Scatter(
                x=edited_st["chock_x_m"],
                y=edited_st["chock_y_m"],
                mode="markers+text",
                marker=dict(size=18, color="#FF4B4B", symbol="square"),
                text=edited_st["winch_id"].astype(str) + " (" + edited_st["chock_id"].astype(str) + ")",
                textposition="top center",
                name="Winch / Basket / Chock",
                hovertemplate="<b>%{text}</b><br>Cima Associata: %{customdata}<extra></extra>",
                customdata=edited_st.get("assigned_line_id", ["N/D"] * len(edited_st))
            )
        )

    fig_st.update_xaxes(range=[0, 100], title="Coordinata X / Longitudinale (%)" if bg_img else "Coordinata X (m)")
    fig_st.update_yaxes(range=[0, 100], title="Coordinata Y / Trasversale (%)" if bg_img else "Coordinata Y (m)")
    fig_st.update_layout(
        title=f"Pianetto Grafico Vetrina - {station_sel}",
        height=450,
        margin=dict(l=20, r=20, t=40, b=20)
    )

    st.markdown("---")
    col_plan1, col_plan2 = st.columns([1, 1])

    with col_plan1:
        st.plotly_chart(fig_st, use_container_width=True)

        buffer = io.StringIO()
        fig_st.write_html(buffer, include_plotlyjs="cdn")
        html_bytes = buffer.getvalue().encode()

        st.download_button(
            label="💾 Scarica Pianetto (Interactive HTML)",
            data=html_bytes,
            file_name=f"pianetto_{station_sel.replace(' ', '_')}.html",
            mime="text/html",
        )

    with col_plan2:
        st.subheader("MSO Identificazione & Annotazione Manuale Pianetto")
        st.write(
            "Disegna o annota a mano sul canvas sottostante per identificare"
            " verricelli, tamburi e numeri cavo sopra la pianetta:"
        )

        if HAS_CANVAS:
            drawing_mode = st.selectbox(
                "Strumento di Disegno:",
                ["freedraw", "circle", "rect", "line", "transform"],
            )
            stroke_color = st.color_picker("Colore Penna", "#FF0000")
            stroke_width = st.slider("Spessore Penna", 1, 10, 3)

            st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                background_image=bg_img if bg_img else None,
                background_color="#f0f2f6" if not bg_img else None,
                height=350,
                width=500,
                drawing_mode=drawing_mode,
                key=f"canvas_{station_sel}",
            )
        else:
            st.warning(
                "Modulo `streamlit-drawable-canvas` non installato. Esegui: `pip"
                " install streamlit-drawable-canvas`"
            )
