"""Line lifecycle wrap-up: exposure, inspections and certificate linkage.

This view deliberately does not invent rope retirement, end-for-ending or
replacement thresholds. Any engineering status must come from manufacturer,
MEG4, class/RO or the vessel SMS criteria once those criteria are configured.
"""

import pandas as pd
import plotly.express as px
import streamlit as st


def ensure_table_exists(conn):
    try:
        cursor = conn.cursor()
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS line_history (
            line_id TEXT PRIMARY KEY,
            line_name TEXT,
            cert_id TEXT,
            accumulated_hours REAL DEFAULT 0.0,
            high_load_hours REAL DEFAULT 0.0,
            max_design_hours REAL,
            fatigue_index REAL DEFAULT 0.0
        );
        """)
        conn.commit()
    except Exception as e:
        st.sidebar.warning(f"Note DB: {e}")


def get_lines_health_status():
    if "db_conn" not in st.session_state or st.session_state.db_conn is None:
        return pd.DataFrame()
    conn = st.session_state.db_conn
    ensure_table_exists(conn)
    try:
        df = pd.read_sql_query("SELECT * FROM line_history", conn)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df

    defaults = {
        "line_name": "Line",
        "line_id": "-",
        "cert_id": "-",
        "accumulated_hours": 0.0,
        "high_load_hours": 0.0,
        "fatigue_index": 0.0,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default
    for col in ["accumulated_hours", "high_load_hours", "fatigue_index"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Status is intentionally informational only until authoritative criteria exist.
    df["Assessment"] = "DATA ONLY — engineering criteria not configured"
    return df


def render_tab_history():
    st.header("📈 Storico & Usura Cavi")
    st.caption("Wrap-up della vita operativa dei cavi: esposizione, carichi, certificato e storico ispezioni.")

    health_df = get_lines_health_status()
    if not health_df.empty:
        fig = px.bar(
            health_df,
            x="line_name",
            y="accumulated_hours",
            hover_data=[c for c in ["high_load_hours", "fatigue_index", "cert_id"] if c in health_df.columns],
            labels={"accumulated_hours": "Accumulated exposure [h]", "line_name": "Line"},
        )
        fig.update_layout(title="Operational exposure by line")
        st.plotly_chart(fig, use_container_width=True)

        summary_cols = [
            "line_id", "line_name", "cert_id", "accumulated_hours",
            "high_load_hours", "fatigue_index", "Assessment",
        ]
        st.dataframe(health_df[[c for c in summary_cols if c in health_df.columns]], use_container_width=True, hide_index=True)
        st.info(
            "⚠️ Nessuna soglia automatica di fine vita o sostituzione viene applicata. "
            "L'app conserva i dati per la valutazione secondo criteri approvati e configurati."
        )
    else:
        st.info("Nessun dato di storico ancora registrato nel database.")
