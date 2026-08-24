"""
views/tab_history.py
Storico ormeggi, degrado cavi e manutenzione predittiva.
"""

import pandas as pd
import plotly.express as px
import streamlit as st


def get_lines_health_status():
    if "db_conn" not in st.session_state:
        return pd.DataFrame()

    conn = st.session_state.db_conn
    df = pd.read_sql_query("SELECT * FROM line_history", conn)

    if df.empty:
        return df

    health_percent = []
    recommendations = []

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
            ]]
        )
    else:
        st.info("Nessun dato di storico ancora registrato nel database.")
