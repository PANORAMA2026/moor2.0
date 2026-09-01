"""Automatic schedule-driven mooring session dashboard."""
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.schedule_runtime import reconcile_schedule
from database.db_manager import get_line_history


def render_tab_mooring_engine():
    st.header("⚡ Automatic Mooring Session Management")

    @st.fragment(run_every="60s")
    def scheduler_fragment():
        result = reconcile_schedule(st.session_state.get("port_schedule", pd.DataFrame()))
        st.session_state["mooring_runtime"] = result
        if result.get("status") == "IN_TRANSIT":
            st.info("⚓ No active port call in the calendar. Monitoring is standing by automatically.")
            return
        session = result.get("session")
        if result.get("operator"):
            st.warning("⚠️ Calendar or mooring setup changed. The existing active record is preserved; operator review is required.")
        if session:
            c = st.columns(5)
            c[0].metric("Port", session.port_name)
            c[1].metric("Session", session.session_id)
            c[2].metric("Status", session.status.value)
            c[3].metric("Setup", session.setup_name or "N/A")
            c[4].metric("Source", session.setup_source)
            st.caption(f"Scheduled: {session.scheduled_start_utc} → {session.scheduled_end_utc}")

    scheduler_fragment()
    st.divider()
    st.subheader("📚 Line History")
    history = get_line_history()
    if history.empty:
        st.caption("No accumulated line history yet.")
    else:
        st.dataframe(history, use_container_width=True)
