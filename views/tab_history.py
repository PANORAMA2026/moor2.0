"""
views/tab_history.py
Storico ormeggi, degrado cavi e manutenzione predittiva.
Uses the canonical line_life_history table instead of the legacy line_history table.
"""

import pandas as pd
import plotly.express as px
import streamlit as st
from database.db_manager import get_line_history


def get_lines_health_status():
    """Return line health calculated from the canonical persistent history."""
    df = get_line_history().copy()
    if df.empty:
        return df

    numeric_defaults = {
        "total_hours": 0.0,
        "accumulated_stress_index": 0.0,
        "wear_percentage": 0,
    }
    for col, default in numeric_defaults.items():
        if col not in df.columns:
            df[col] = default
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)

    # Preserve the existing operational health concept while using the canonical
    # accumulated-history fields. The limits are intentionally explicit so the
    # result is not confused with a manufacturer-certified remaining-life value.
    max_design_hours = 2000.0
    stress_reference = 300.0
    health_percent = []
    recommendations = []

    for _, row in df.iterrows():
        hours_used_pct = max(0.0, float(row["total_hours"])) / max_design_hours * 100.0
        stress_pct = max(0.0, float(row["accumulated_stress_index"])) / stress_reference * 100.0
        recorded_wear = max(0.0, float(row.get("wear_percentage", 0.0)))
        wear_pct = max(hours_used_pct, stress_pct, recorded_wear)
        remaining_health = max(0.0, 100.0 - wear_pct)
        health_percent.append(round(remaining_health, 2))

        if remaining_health <= 20.0:
            recommendations.append("🚨 SOSTITUZIONE IMMINENTE: richiedere valutazione tecnica.")
        elif remaining_health <= 40.0:
            recommendations.append("⚠️ ISPEZIONE: programmare verifica e valutare end-for-end se applicabile.")
        else:
            recommendations.append("✅ Nessuna azione automatica indicata dal solo storico.")

    df["Health_Percent"] = health_percent
    df["Recommendation"] = recommendations
    return df


def render_tab_history():
    st.header("📈 Registro Storico Usura & Suggerimento Sostituzione Cavi")
    st.caption(
        "Lo storico operativo proviene da line_life_history. L'indice Health è un indicatore interno "
        "e non rappresenta una certificazione di vita residua del cavo."
    )

    health_df = get_lines_health_status()
    if health_df.empty:
        st.info("Nessun dato di storico ancora registrato nel database.")
        return

    fig_health = px.bar(
        health_df,
        x="line_id",
        y="Health_Percent",
        color="Health_Percent",
        color_continuous_scale=["red", "yellow", "green"],
        range_color=[0, 100],
    )
    fig_health.add_hline(
        y=20,
        line_dash="dash",
        line_color="red",
        annotation_text="Soglia di attenzione (20%)",
    )
    st.plotly_chart(fig_health, use_container_width=True)

    cols_to_display = [
        "line_id",
        "last_port",
        "current_setup",
        "applied_tension_mbl_pct",
        "total_hours",
        "accumulated_stress_index",
        "wear_percentage",
        "Health_Percent",
        "status",
        "last_inspection",
        "Recommendation",
    ]
    available_cols = [c for c in cols_to_display if c in health_df.columns]
    st.dataframe(health_df[available_cols], use_container_width=True)
