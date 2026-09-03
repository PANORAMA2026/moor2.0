"""Operational control page for selecting the active mooring setup.

The calendar remains authoritative for the port call. This page only allows an
operator to replace the automatically selected setup for the current session.
The override is persisted on the session and therefore survives Streamlit
reruns and the automatic scheduler refresh.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from core.auth import has_role, logout_button, require_login
from core.schedule_runtime import reconcile_schedule
from core.setup_store import list_setup_names, load_setup
from database.mooring_session_repository import load_active_or_scheduled, save_session


st.set_page_config(page_title="Mooring Command Control", layout="wide")
if not require_login():
    st.stop()
logout_button()

st.title("🎛️ Mooring Command Control")
st.caption(
    "Controllo operativo della configurazione attiva: il calendario determina il port call; "
    "l'operatore può sostituire il mooring setup quando necessario."
)

if not has_role("ADMIN", "CHIEF_OFFICER"):
    st.error("Questo controllo è riservato a Administrator / Chief Officer / Master.")
    st.stop()

# Reconcile first so the page sees the same active session as the automatic engine.
schedule = st.session_state.get("port_schedule", pd.DataFrame())
if isinstance(schedule, pd.DataFrame) and not schedule.empty:
    runtime = reconcile_schedule(schedule)
    st.session_state["mooring_runtime"] = runtime
else:
    runtime = st.session_state.get("mooring_runtime", {})

sessions = load_active_or_scheduled()
active = [s for s in sessions if s.status.value == "ACTIVE"]

if not active:
    st.info("Nessuna mooring session ACTIVE. Il controllo sarà disponibile automaticamente quando il calendario entra in un port call.")
    if sessions:
        st.markdown("### Sessioni programmate")
        st.dataframe(
            pd.DataFrame([
                {
                    "Session": s.session_id,
                    "Port": s.port_name,
                    "Status": s.status.value,
                    "Setup": s.setup_name or "N/A",
                    "Source": s.setup_source,
                    "ETA": s.scheduled_start_utc,
                    "ETD": s.scheduled_end_utc,
                }
                for s in sessions
            ]),
            use_container_width=True,
            hide_index=True,
        )
    st.stop()

# Normally there is one active calendar call. If there are several, the operator
# explicitly selects which active session to control.
session_labels = [
    f"{s.session_id} · {s.port_name} · {s.setup_name or 'N/A'} · {s.setup_source}"
    for s in active
]
selected_label = st.selectbox("Active mooring session", session_labels)
session = active[session_labels.index(selected_label)]

st.markdown("### 📌 Active session")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Port", session.port_name)
c2.metric("Status", session.status.value)
c3.metric("Current setup", session.setup_name or "N/A")
c4.metric("Setup source", session.setup_source)
st.caption(
    f"Session {session.session_id} · scheduled {session.scheduled_start_utc} → {session.scheduled_end_utc}"
)

setups = list_setup_names(session.port_name)
if not setups:
    st.error(f"Nessun mooring setup configurato per {session.port_name}.")
    st.stop()

current_setup = session.setup_name if session.setup_name in setups else setups[0]
selected_setup = st.selectbox(
    "Nuovo setup da applicare",
    setups,
    index=setups.index(current_setup),
    key=f"command_setup_{session.session_id}",
)

setup_df = load_setup(session.port_name, selected_setup)
if setup_df.empty:
    st.error("Il setup selezionato è vuoto e non può essere applicato.")
    st.stop()

m1, m2, m3 = st.columns(3)
m1.metric("Connections", len(setup_df))
m2.metric("FWD", int((setup_df["station"].astype(str).str.upper() == "FWD").sum()))
m3.metric("AFT", int((setup_df["station"].astype(str).str.upper() == "AFT").sum()))

st.dataframe(
    setup_df[[
        c for c in [
            "line_id", "station", "line_type", "winch_id", "winch_slot",
            "fairlead_id", "bollard_id", "bollard_station", "side"
        ] if c in setup_df.columns
    ]],
    use_container_width=True,
    hide_index=True,
)

st.markdown("### 📝 Operator override")
if session.setup_source == "OPERATOR_OVERRIDE":
    st.warning(
        f"L'attuale configurazione è già un **OPERATOR OVERRIDE** ({session.setup_name}). "
        "Il calendario continuerà a essere monitorato separatamente."
    )

reason = st.text_area(
    "Motivo della modifica",
    placeholder="Esempio: vento previsto dal lato porto; setup alternativo selezionato secondo piano operativo.",
    key=f"override_reason_{session.session_id}",
)

apply = st.button(
    "⚓ Applica setup alla sessione attiva",
    type="primary",
    use_container_width=True,
    disabled=(selected_setup == session.setup_name and session.setup_source != "OPERATOR_OVERRIDE"),
)

if apply:
    reason = reason.strip()
    if not reason:
        st.error("Inserire il motivo della modifica prima di applicare l'override.")
    else:
        previous = session.setup_name or "N/A"
        timestamp = datetime.now(timezone.utc).isoformat()
        audit_note = (
            f"[{timestamp}] OPERATOR_OVERRIDE: setup {previous} -> {selected_setup}. "
            f"Reason: {reason}"
        )
        session.setup_name = selected_setup
        session.setup_source = "OPERATOR_OVERRIDE"
        session.notes = f"{session.notes}\n{audit_note}".strip()
        save_session(session)
        st.session_state["active_setup_name"] = selected_setup
        st.session_state["last_setup_override"] = {
            "session_id": session.session_id,
            "previous_setup": previous,
            "new_setup": selected_setup,
            "reason": reason,
            "timestamp_utc": timestamp,
        }
        st.success(
            f"Setup **{selected_setup}** applicato alla sessione {session.session_id}. "
            "La configurazione è ora marcata OPERATOR_OVERRIDE."
        )
        st.rerun()

last_override = st.session_state.get("last_setup_override")
if last_override and last_override.get("session_id") == session.session_id:
    st.divider()
    st.markdown("### ✅ Last override recorded")
    st.json(last_override)

st.info(
    "Il cambio setup non modifica il calendario ETA/ETD e non costituisce conferma che le cime siano "
    "fisicamente made fast. Il solver utilizzerà il setup selezionato solo come configurazione di calcolo."
)
