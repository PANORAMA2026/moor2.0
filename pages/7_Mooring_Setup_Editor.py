"""Operator-facing mooring setup editor."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.constants import DEFAULT_SHIP
from core.auth import require_login, logout_button
from core.berth_profiles import get_berth_profile
from core.mooring_equipment import get_fairleads, FWD_WINCH_IDS, AFT_WINCH_IDS
from core.setup_store import delete_setup, ensure_normal_setup, list_setup_names, load_setup, save_setup, validate_setup

st.set_page_config(page_title="Mooring Setup Editor", layout="wide")
require_login(); logout_button()

PORT = "Ensenada Pier #2"
ensure_normal_setup(PORT)
st.title("⚓ Mooring Setup Editor")
st.caption("Topologia operativa: Winch → Fairlead → Line → Bollard. Un winch può servire più linee e una bitta può ricevere più linee; i limiti dipendono dall'equipaggiamento reale.")

setup_names = list_setup_names(PORT)
selected_setup = st.selectbox("Setup", setup_names, key="setup_editor_selected")
df = load_setup(PORT, selected_setup)
if "winch_id" in df.columns: df["winch_id"] = df["winch_id"].fillna("")
if "winch_slot" not in df.columns: df["winch_slot"] = pd.NA

fairleads = list(get_fairleads(side="PORT"))
profile = get_berth_profile(PORT)
bollards = list(profile.get("points", ()))
bollard_keys={(p.measurement_station.upper(),str(p.bollard_id).upper()) for p in bollards}

with st.expander("📋 Stato del setup", expanded=True):
    c1,c2,c3,c4=st.columns(4)
    c1.metric("Porto",PORT); c2.metric("Setup",selected_setup); c3.metric("Connessioni",len(df)); c4.metric("Nave",DEFAULT_SHIP.get("Name","N/A"))

st.subheader("✏️ Connessioni")
st.info("Ogni winch è un punto fisico che può gestire più linee. La posizione/slot della singola linea sul winch va inserita solo quando verificata. Analogamente, più linee possono condividere la stessa bitta, entro il relativo SWL/MWLL e le regole di bordo.")

editor_columns=["line_id","station","line_type","winch_id","winch_slot","fairlead_id","bollard_id","bollard_station","side"]
edit_df=df[editor_columns].copy()
winch_options=[""]+list(FWD_WINCH_IDS)+list(AFT_WINCH_IDS)
line_type_options=["HEAD","SPRING","STERN"]

edited=st.data_editor(edit_df,use_container_width=True,hide_index=True,num_rows="fixed",column_config={
    "line_id":st.column_config.TextColumn("Line ID",disabled=True),
    "station":st.column_config.SelectboxColumn("Station",options=["FWD","AFT"],disabled=True),
    "line_type":st.column_config.SelectboxColumn("Line type",options=line_type_options),
    "winch_id":st.column_config.SelectboxColumn("Winch",options=winch_options),
    "winch_slot":st.column_config.NumberColumn("Winch slot",min_value=1,max_value=4,step=1,format="%d"),
    "fairlead_id":st.column_config.SelectboxColumn("Fairlead",options=[p.point_id for p in fairleads]),
    "bollard_id":st.column_config.TextColumn("Bollard"),
    "bollard_station":st.column_config.SelectboxColumn("Bollard station",options=["FWD","AFT"]),
    "side":st.column_config.SelectboxColumn("Side",options=["PORT","STBD"]),
},key="mooring_setup_editor")

errors=validate_setup(edited,fairlead_ids={p.point_id for p in fairleads},bollard_keys=bollard_keys)
for _,row in edited.iterrows():
    line=str(row["line_id"]); station=str(row["station"]).upper(); winch=str(row["winch_id"]).strip();
    if winch and ((station=="FWD" and winch not in FWD_WINCH_IDS) or (station=="AFT" and winch not in AFT_WINCH_IDS)): errors.append(f"{line}: {winch} does not belong to {station}")
    fl=next((p for p in fairleads if p.point_id==str(row["fairlead_id"])),None)
    if fl is not None and fl.station.upper()!=station: errors.append(f"{line}: fairlead belongs to {fl.station}, not {station}")
    if str(row["bollard_station"]).upper()!=station: errors.append(f"{line}: bollard station does not match line station")
    slot=row.get("winch_slot")
    if winch and pd.isna(slot): errors.append(f"{line}: select a winch slot (1-4) when a winch is assigned")

# Duplicate slot means two lines assigned to the same physical winch slot.
assigned=edited[edited["winch_id"].fillna("").astype(str).str.strip()!=""].copy()
if not assigned.empty:
    assigned["slot_num"]=pd.to_numeric(assigned["winch_slot"],errors="coerce")
    dup=assigned.dropna(subset=["slot_num"]).duplicated(subset=["winch_id","slot_num"],keep=False)
    for _,r in assigned[dup].iterrows(): errors.append(f"{r['line_id']}: winch {r['winch_id']} slot {int(r['slot_num'])} is already assigned to another line")

if errors:
    st.error("❌ Setup non valido")
    for e in dict.fromkeys(errors): st.write(f"• {e}")
else: st.success("✅ Topologia coerente. Shared winches/bollards are allowed; capacity/SWL checks are handled only when verified equipment limits are available.")

st.subheader("💾 Salva come alternativa")
new_name=st.text_input("Nome nuova alternativa",value="Alternative 01" if selected_setup=="Normal" else f"{selected_setup} Copy")
c1,c2,c3=st.columns(3)
with c1:
    if st.button("💾 Salva nuova alternativa",type="primary",use_container_width=True):
        name=str(new_name).strip()
        if name=="Normal": st.error("Il nome Normal è riservato.")
        elif not name: st.error("Inserire un nome.")
        elif errors: st.error("Correggere prima gli errori.")
        else: save_setup(PORT,name,edited,source="OPERATOR"); st.success(f"✅ {name} salvato."); st.rerun()
with c2:
    if st.button("🔄 Ricarica",use_container_width=True): st.rerun()
with c3:
    if selected_setup!="Normal" and st.button("🗑️ Elimina",use_container_width=True): delete_setup(PORT,selected_setup); st.rerun()

st.divider(); st.subheader("🔎 Preview")
preview=edited.copy(); preview["connection"]=(preview["winch_id"].fillna("").astype(str)+" [slot "+preview["winch_slot"].fillna("").astype(str)+"] → "+preview["fairlead_id"].astype(str)+" → "+preview["line_id"].astype(str)+" → "+preview["bollard_station"].astype(str)+":"+preview["bollard_id"].astype(str))
st.dataframe(preview[["line_id","station","line_type","connection"]],use_container_width=True,hide_index=True)

st.caption("Engineering note: shared equipment is intentional. A winch-to-line relationship is many-to-one in the topology, while bollard loading is also many-to-one. Individual SWL/MWLL and permitted line count must come from verified berth/equipment documentation.")
