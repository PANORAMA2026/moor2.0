"""Operator-facing mooring setup editor.

This page edits topology only. It does not alter the mooring solver or the
reference geometry. Saved alternatives are persistent in SQLite and can later
be consumed by the automatic setup selector.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import DEFAULT_SHIP
from core.auth import require_login, logout_button
from core.berth_profiles import get_berth_profile
from core.mooring_equipment import get_fairleads
from core.setup_store import (
    delete_setup,
    ensure_normal_setup,
    list_setup_names,
    load_setup,
    save_setup,
    validate_setup,
)

st.set_page_config(page_title="Mooring Setup Editor", layout="wide")
require_login()
logout_button()

PORT = "Ensenada Pier #2"
ensure_normal_setup(PORT)

st.title("⚓ Mooring Setup Editor")
st.caption(
    "Editor operativo della topologia: Winch → Fairlead → Line → Bollard. "
    "Il setup Normal rimane la configurazione di riferimento e non viene modificato."
)

setup_names = list_setup_names(PORT)
selected_setup = st.selectbox("Setup da visualizzare/modificare", setup_names, key="setup_editor_selected")
df = load_setup(PORT, selected_setup)

# Fill missing winch IDs from the current row order only as an operator convenience.
# They remain editable and are never treated as certified equipment data.
if "winch_id" in df.columns:
    df["winch_id"] = df["winch_id"].fillna("")

fairleads = list(get_fairleads(side="PORT"))
fairlead_by_station = {
    "FWD": [p.point_id for p in fairleads if p.station == "FWD"],
    "AFT": [p.point_id for p in fairleads if p.station == "AFT"],
}
profile = get_berth_profile(PORT)
bollards = list(profile.get("points", ()))
bollard_ids = {
    "FWD": [p.bollard_id for p in bollards if p.measurement_station == "FWD"],
    "AFT": [p.bollard_id for p in bollards if p.measurement_station == "AFT"],
}

with st.expander("📋 Stato del setup", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Porto", PORT)
    c2.metric("Setup", selected_setup)
    c3.metric("Connessioni", len(df))
    c4.metric("Nave", DEFAULT_SHIP.get("Name", "N/A"))

st.subheader("✏️ Modifica connessioni")
st.info(
    "Puoi modificare Fairlead e Bollard per creare una variante del piano. "
    "La colonna Winch è predisposta per l'associazione ai verricelli reali; fino a quando "
    "l'inventario delle stazioni non sarà completo, non viene assunta come dato certificato."
)

editor_columns = [
    "line_id", "station", "line_type", "winch_id", "fairlead_id",
    "bollard_id", "bollard_station", "side",
]
edit_df = df[editor_columns].copy()

# Keep the reference topology readable while making the selectable fields editable.
line_type_options = ["HEAD", "SPRING", "STERN"]
winch_options = [""] + [f"W{i}" for i in range(1, 25)]
side_options = ["PORT", "STBD"]

edited = st.data_editor(
    edit_df,
    use_container_width=True,
    hide_index=True,
    num_rows="fixed",
    column_config={
        "line_id": st.column_config.TextColumn("Line ID", disabled=True),
        "station": st.column_config.SelectboxColumn("Station", options=["FWD", "AFT"], disabled=True),
        "line_type": st.column_config.SelectboxColumn("Line type", options=line_type_options),
        "winch_id": st.column_config.SelectboxColumn("Winch", options=winch_options),
        "fairlead_id": st.column_config.SelectboxColumn("Fairlead", options=[p.point_id for p in fairleads]),
        "bollard_id": st.column_config.TextColumn("Bollard"),
        "bollard_station": st.column_config.SelectboxColumn("Bollard station", options=["FWD", "AFT"]),
        "side": st.column_config.SelectboxColumn("Side", options=side_options),
    },
    key="mooring_setup_editor",
)

# Dynamic validation: fairlead and bollard must belong to the same station.
errors = validate_setup(
    edited,
    fairlead_ids={p.point_id for p in fairleads},
    bollard_keys={(p.measurement_station.upper(), str(p.bollard_id).upper()) for p in bollards},
)
for _, row in edited.iterrows():
    line = str(row["line_id"])
    station = str(row["station"]).upper()
    fl = next((p for p in fairleads if p.point_id == str(row["fairlead_id"])), None)
    if fl is not None and fl.station.upper() != station:
        errors.append(f"{line}: fairlead {fl.point_id} belongs to {fl.station}, not {station}")
    if str(row["bollard_station"]).upper() != station:
        errors.append(f"{line}: bollard station does not match line station")

if errors:
    st.error("❌ Setup non valido")
    for error in dict.fromkeys(errors):
        st.write(f"• {error}")
else:
    st.success("✅ Topologia valida: tutte le connessioni puntano a fairlead e bitte esistenti e coerenti con la station.")

st.subheader("💾 Salva come alternativa")
new_name = st.text_input(
    "Nome nuova alternativa",
    value="Alternative 01" if selected_setup == "Normal" else f"{selected_setup} Copy",
    help="Il setup Normal non viene sovrascritto: salva sempre una nuova variante.",
)

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("💾 Salva nuova alternativa", type="primary", use_container_width=True):
        name = str(new_name).strip()
        if name == "Normal":
            st.error("Il nome Normal è riservato al setup di riferimento.")
        elif not name:
            st.error("Inserire un nome per l'alternativa.")
        elif errors:
            st.error("Correggere prima gli errori di validazione.")
        else:
            save_setup(PORT, name, edited, source="OPERATOR")
            st.success(f"✅ {name} salvato in modo persistente.")
            st.rerun()

with c2:
    if st.button("🔄 Ricarica setup", use_container_width=True):
        st.rerun()

with c3:
    if selected_setup != "Normal" and st.button("🗑️ Elimina alternativa", use_container_width=True):
        delete_setup(PORT, selected_setup)
        st.success(f"{selected_setup} eliminato.")
        st.rerun()

st.divider()
st.subheader("🔎 Preview della connessione")
preview = edited.copy()
preview["connection"] = (
    preview["winch_id"].fillna("").astype(str) + " → "
    + preview["fairlead_id"].astype(str) + " → "
    + preview["line_id"].astype(str) + " → "
    + preview["bollard_station"].astype(str) + ":" + preview["bollard_id"].astype(str)
)
st.dataframe(
    preview[["line_id", "station", "line_type", "connection"]],
    use_container_width=True,
    hide_index=True,
)

st.caption(
    "Engineering note: questo editor gestisce la topologia operativa. Le coordinate dei fairlead "
    "rimangono separate e attualmente sono REFERENCE; la geometria engineering-grade sarà aggiornata "
    "dopo la misura delle distanze dal centro nave."
)
