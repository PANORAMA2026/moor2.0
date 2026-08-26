"""
views/tab_history.py
Storico ormeggi, degrado cavi e manutenzione predittiva.
"""

import pandas as pd
import plotly.express as px
import streamlit as st


def ensure_table_exists(conn):
    """Crea la tabella 'line_history' se non esiste ancora nel database."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS line_history (
                line_id TEXT PRIMARY KEY,
                line_name TEXT,
                cert_id TEXT,
                accumulated_hours REAL DEFAULT 0.0,
                high_load_hours REAL DEFAULT 0.0,
                max_design_hours REAL DEFAULT 2000.0,
                fatigue_index REAL DEFAULT 0.0
            )
        """)
        conn.commit()
    except Exception as e:
        st.warning(f"Errore durante l'inizializzazione del database: {e}")


def get_lines_health_status():
    if "db_conn" not in st.session_state or st.session_state.db_conn is None:
        return pd.DataFrame()

    conn = st.session_state.db_conn
    ensure_table_exists(conn)

    try:
        df = pd.read_sql_query("SELECT * FROM line_history", conn)
    except Exception as e:
        st.warning(f"Impossibile leggere i dati storici dal database: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    health_percent = []
    recommendations = []

    # Garanzia presenza colonne minime richieste per il calcolo
    for col, default_val in [
        ("max_design_hours", 2000.0),
        ("accumulated_hours", 0.0),
        ("fatigue_index", 0.0),
    ]:
        if col not in df.columns:
            df[col] = default_val
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default_val)

    for _, row in df.iterrows():
        max_h = (
            row["max_design_hours"] if row["max_design_hours"] > 0 else 2000.0
        )
        hours_used_pct = (row["accumulated_hours"] / max_h) * 100.0
        fatigue_pct = (row["fatigue_index"] / 300.0) * 100.0
        wear_pct = max(hours_used_pct, fatigue_pct)
        remaining_health = max(0.0, 100.0 - wear_pct)

        health_percent.append(remaining_health)

        if remaining_health <= 20.0:
            recommendations.append(
                "🚨 SOSTITUZIONE IMMINENTE: Cavo a fine vita utile!"
            )
        elif remaining_health <= 40.0:
            recommendations.append(
                "⚠️ ISPEZIONE: Valutare rotazione testa-coda (End-for-End)."
            )
        else:
            recommendations.append("✅ IDONEO: Condizioni operative regolari.")

    df["Health_Percent"] = health_percent
    df["Recommendation"] = recommendations
    return df


def render_tab_history():
    st.header("📈 Registro Storico Usura & Suggerimento Sostituzione Cavi")

    health_df = get_lines_health_status()
    if not health_df.empty:
        # Se mancano colonne opzionali per la visualizzazione le inizializza vuote
        for col in ["line_name", "line_id", "cert_id", "high_load_hours"]:
            if col not in health_df.columns:
                health_df[col] = "-"

        fig_health = px.bar(
            health_df,
            x="line_name",
            y="Health_Percent",
            color="Health_Percent",
            color_continuous_scale=["red", "yellow", "green"],
            range_color=[0, 100],
        )
        fig_health.add_hline(
            y=20,
            line_dash="dash",
            line_color="red",
            annotation_text="Soglia Sostituzione (20%)",
        )
        st.plotly_chart(fig_health, use_container_width=True)

        st.dataframe(
            health_df[[
                "line_id",
                "line_name",
                "cert_id",
                "accumulated_hours",
                "high_load_hours",
                "Health_Percent",
                "Recommendation",
            ]],
            use_container_width=True,
        )
    else:
        st.info("Nessun dato di storico ancora registrato nel database.")
