"""
views/tab_plans.py
Pianetti Mooring Station, esportazione HTML e lavagna interattiva per annotazioni MSO.
"""

import io
import plotly.graph_objects as go
import streamlit as st

try:
    from streamlit_drawable_canvas import st_canvas

    HAS_CANVAS = True
except ImportError:
    HAS_CANVAS = False


def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio, Pianetti & Annotazione")

    if "mooring_stations" not in st.session_state:
        st.session_state.mooring_stations = {}

    station_sel = st.selectbox(
        "Seleziona Stazione d'Ormeggio",
        list(st.session_state.mooring_stations.keys()),
    )
    if not station_sel:
        st.warning("Nessuna stazione trovata.")
        return

    st_df = st.session_state.mooring_stations[station_sel]

    st.subheader(f"⚙️ Configurazione Dati: {station_sel}")
    edited_st = st.data_editor(
        st_df,
        num_rows="dynamic",
        use_container_width=True,
        key=f"edit_st_{station_sel}",
    )
    st.session_state.mooring_stations[station_sel] = edited_st

    fig_st = go.Figure()
    fig_st.add_trace(
        go.Scatter(
            x=edited_st["chock_x_m"],
            y=edited_st["chock_y_m"],
            mode="markers+text",
            marker=dict(size=18, color="darkorange", symbol="square"),
            text=edited_st["winch_id"] + " (" + edited_st["chock_id"] + ")",
            textposition="top center",
            name="Winch / Chock Position",
        )
    )

    fig_st.update_layout(
        title=f"Pianetto Grafico Vetrina - {station_sel}",
        xaxis_title="Coordinata X Longitudinale (m)",
        yaxis_title="Coordinata Y Trasversale (m)",
        height=380,
    )

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
            " verricelli, tamburi e numeri cavo:"
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
                background_color="#f0f2f6",
                height=300,
                width=500,
                drawing_mode=drawing_mode,
                key=f"canvas_{station_sel}",
            )
        else:
            st.warning(
                "Modulo `streamlit-drawable-canvas` non installato. Esegui: `pip"
                " install streamlit-drawable-canvas`"
            )
