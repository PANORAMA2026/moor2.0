"""
views/tab_plans.py
Pianetti Mooring Station: Gestione Usura Cime & Assegnazione Posizioni Ormeggio.
"""

import os
import pandas as pd
import streamlit as st
from PIL import Image
from datetime import date

from database.db_manager import (
    get_line_history,
    save_mooring_station_components,
    get_mooring_station_components,
    save_line_history,
    assign_line_to_slot,
    load_certificates_from_db
)

# -----------------------------------------------------------------------------
# REFERENCE LIBRARY ISO 2307 / CI 2001 & AI SIMULATION
# -----------------------------------------------------------------------------
DAMAGE_REFERENCE_LIBRARY = {
    "Abrasione Superficiale": {
        "image_path": "assets/ref_abrasion.jpg",
        "description": "Pelosità superficiale dovuta a sfregamento su passacavi o tamburi ruvidi.",
        "iso_severity": "MEDIA",
        "default_wear_impact": 20
    },
    "Rottura Legnoli / Capi Tranciati": {
        "image_path": "assets/ref_strand_break.jpg",
        "description": "Rottura di uno o più legnoli principali. Riduzione diretta di MBL.",
        "iso_severity": "CRITICA",
        "default_wear_impact": 50
    },
    "Fusione da Calore / Attrito": {
        "image_path": "assets/ref_glazing.jpg",
        "description": "Vetrificazione del materiale sintetico per scorrimento o carico d'impatto.",
        "iso_severity": "ALTA",
        "default_wear_impact": 35
    },
    "Degrado UV / Decolorazione": {
        "image_path": "assets/ref_uv_damage.jpg",
        "description": "Irrigidimento e polverizzazione delle fibre esterne per esposizione solare.",
        "iso_severity": "LIEVE",
        "default_wear_impact": 15
    }
}

def analyze_damage_with_ai(image_file):
    """Simula l'analisi della foto con rete neurale Computer Vision."""
    return {
        "damage_type": "Abrasione Superficiale",
        "confidence": 88.5,
        "suggested_extra_wear": 20,
        "severity": "MEDIA"
    }

# -----------------------------------------------------------------------------
# PRESET ESTRUTTURALE PER STAZIONI DI ORMEGGIO
# -----------------------------------------------------------------------------
DEFAULT_STATION_PRESETS = {
    "Prua (Forward Station)": [
        {"slot_id": "W1 (Drum A)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W1 (Drum B)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W2 (Drum A)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W2 (Drum B)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "Cesta Prua 1", "comp_type": "BASKET", "assigned_line": "Nessuna"},
        {"slot_id": "Cesta Prua 2", "comp_type": "BASKET", "assigned_line": "Nessuna"},
    ],
    "Poppa (Aft Station)": [
        {"slot_id": "W3 (Drum A)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W3 (Drum B)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W4 (Drum A)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "W4 (Drum B)", "comp_type": "WINCH", "assigned_line": "Nessuna"},
        {"slot_id": "Cesta Poppa 1", "comp_type": "BASKET", "assigned_line": "Nessuna"},
    ]
}

# -----------------------------------------------------------------------------
# GESTIONE DATABASE & SINCRONIZZAZIONE CIME
# -----------------------------------------------------------------------------
def load_station_slots(station_name: str) -> pd.DataFrame:
    """Carica gli slot della stazione dal DB o applica il preset di default."""
    db_data = get_mooring_station_components(station_name)
    records = []

    if isinstance(db_data, pd.DataFrame) and not db_data.empty:
        records = db_data.to_dict(orient="records")
    elif isinstance(db_data, list) and len(db_data) > 0:
        records = db_data

    if not records and station_name in DEFAULT_STATION_PRESETS:
        records = DEFAULT_STATION_PRESETS[station_name]
        save_mooring_station_components(records, station_name)

    clean_records = []
    for r in records:
        clean_records.append({
            "slot_id": r.get("slot_id", r.get("comp_id", "SLOT")),
            "comp_type": r.get("comp_type", "WINCH"),
            "assigned_line": r.get("assigned_line", r.get("line_drum_a", "Nessuna"))
        })

    return pd.DataFrame(clean_records)


def update_line_wear_in_db(line_id: str, new_wear: int, status: str, note: str):
    """Aggiorna lo stato di usura della cima nell'inventario globale."""
    if not line_id or line_id == "Nessuna":
        return

    clean_id = line_id.split(" ")[0]
    lines_df = get_line_history()
    id_col = "line_id" if "line_id" in lines_df.columns else "id"

    if not lines_df.empty and clean_id in lines_df[id_col].astype(str).values:
        lines_df.loc[lines_df[id_col].astype(str) == clean_id, "wear_percentage"] = new_wear
        lines_df.loc[lines_df[id_col].astype(str) == clean_id, "status"] = status
        lines_df.loc[lines_df[id_col].astype(str) == clean_id, "last_inspection"] = str(date.today())
        lines_df.loc[lines_df[id_col].astype(str) == clean_id, "notes"] = note
    else:
        new_row = pd.DataFrame([{
            "line_id": clean_id,
            "last_port": "N/D",
            "current_setup": "N/D",
            "applied_tension_mbl_pct": 0.0,
            "total_hours": 0.0,
            "accumulated_stress_index": 0.0,
            "wear_percentage": new_wear,
            "status": status,
            "last_inspection": str(date.today()),
            "notes": note,
            "last_auto_sync": str(date.today())
        }])
        lines_df = pd.concat([lines_df, new_row], ignore_index=True)

    save_line_history(lines_df)

# -----------------------------------------------------------------------------
# DIALOG AI INSPECTION PER CIMA
# -----------------------------------------------------------------------------
@st.dialog("📸 Ispezione & Analisi Danno Cima", width="large")
def open_line_inspection_dialog(line_id: str, current_wear: int):
    st.write(f"Ispezione Cima: **{line_id}**")
    
    img_file = st.camera_input("Scatta foto al danno della cima")
    if not img_file:
        img_file = st.file_uploader("Oppure carica foto dalla galleria", type=["jpg", "png", "jpeg"])

    if img_file:
        ai_res = analyze_damage_with_ai(img_file)
        ref_data = DAMAGE_REFERENCE_LIBRARY.get(ai_res["damage_type"], {
            "image_path": None, "description": "Nessuna scheda standard", "iso_severity": "N/D", "default_wear_impact": 20
        })

        st.markdown("---")
        col_snap, col_ref = st.columns(2)
        with col_snap:
            st.caption("📷 Foto Danno Rilevato")
            st.image(Image.open(img_file), use_container_width=True)
        with col_ref:
            st.caption(f"📚 Catalogo Ufficiale ISO: **{ai_res['damage_type']}**")
            if ref_data["image_path"] and os.path.exists(ref_data["image_path"]):
                st.image(Image.open(ref_data["image_path"]), use_container_width=True)
            else:
                st.info(f"**Descrizione:** {ref_data['description']}\n\n**Gravità ISO:** `{ref_data['iso_severity']}`")

        st.markdown("---")
        st.write("**Valutazione Incremento Usura Cima:**")

        c_low, c_ai, c_high = st.columns(3)
        extra_wear = ai_res["suggested_extra_wear"]
        
        if c_low.button("📉 Lieve (+15%)"):
            extra_wear = 15
        if c_ai.button(f"🤖 AI (+{ai_res['suggested_extra_wear']}%)"):
            extra_wear = ai_res["suggested_extra_wear"]
        if c_high.button("📈 Severo (+45%)"):
            extra_wear = 45

        new_total_wear = min(100, current_wear + extra_wear)
        st.metric("Nuova Usura Totale Cima", f"{new_total_wear}%", delta=f"+{extra_wear}%")

        if st.button("💾 Salvataggio Permanente Ispezione Cima", type="primary", use_container_width=True):
            status_str = "CRITICO" if new_total_wear > 60 else "USURATO"
            note_str = f"AI: {ai_res['damage_type']} (+{extra_wear}%)"
            
            update_line_wear_in_db(line_id, new_total_wear, status_str, note_str)
            st.success(f"Usura della cima {line_id} aggiornata al {new_total_wear}%!")
            st.rerun()

# -----------------------------------------------------------------------------
# MAIN TAB PLANS
# -----------------------------------------------------------------------------
def render_tab_plans():
    st.header("🪢 Gestione Cime & Assegnazione Posizioni d'Ormeggio")

    stations_list = list(DEFAULT_STATION_PRESETS.keys())
    station_sel = st.selectbox("Seleziona Stazione d'Ormeggio", stations_list, key="selected_mooring_station")
    st_code = "FWD" if "Prua" in station_sel else "AFT"

    # Caricamento Slot Stazione e Storico Cime
    slots_df = load_station_slots(station_sel)
    lines_history_df = get_line_history()
    certs_df = load_certificates_from_db()

    # Elenco cime disponibili da certificati/inventario
    available_lines = ["Nessuna"]
    if not certs_df.empty and "cert_id" in certs_df.columns:
        for _, c_row in certs_df.iterrows():
            c_id = str(c_row["cert_id"])
            c_mat = str(c_row.get("material", ""))
            c_dia = str(c_row.get("diameter_mm", ""))
            desc = f"{c_id} ({c_mat} - {c_dia}mm)" if c_mat else c_id
            available_lines.append(desc)

    # AZIONI RAPIDE
    st.markdown("---")
    c_act1, c_act2 = st.columns([1, 1])
    
    with c_act1:
        if st.button("🔄 Ripristina Layout Posizioni Standard", use_container_width=True):
            slots_df = pd.DataFrame(DEFAULT_STATION_PRESETS[station_sel])
            save_mooring_station_components(slots_df.to_dict(orient="records"), station_sel)
            st.success("Layout stazioni ripristinato!")
            st.rerun()

    with c_act2:
        if st.button("✅ Ispezione Rapida: Tutte le Cime OK", type="primary", use_container_width=True):
            for _, r in slots_df.iterrows():
                line = r["assigned_line"]
                if line != "Nessuna":
                    update_line_wear_in_db(line, 0, "OTTIMO", "Ispezione Standard OK")
            st.success("Tutte le cime attive confermate in ottimo stato!")
            st.rerun()

    # PANNELLO CIME PER SLOT
    st.markdown("### ⚓ Cime Attive in Stazione")

    has_changes = False

    for idx, row in slots_df.iterrows():
        slot_id = str(row["slot_id"])
        comp_type = str(row["comp_type"])
        curr_line = str(row["assigned_line"])

        # Recupera usura e stato attuale della cima dal DB inventario
        line_wear = 0
        line_status = "NON ASSEGNATA"
        
        if curr_line != "Nessuna":
            clean_id = curr_line.split(" ")[0]
            if not lines_history_df.empty:
                id_col = "line_id" if "line_id" in lines_history_df.columns else "id"
                match = lines_history_df[lines_history_df[id_col].astype(str) == clean_id]
                if not match.empty:
                    line_wear = int(match.iloc[0].get("wear_percentage", 0))
                    line_status = str(match.iloc[0].get("status", "OTTIMO"))

        # Indicatore visivo usura cima
        if curr_line == "Nessuna":
            badge = "⚪"
        elif line_wear < 40:
            badge = "🟢"
        elif line_wear < 70:
            badge = "🟡"
        else:
            badge = "🔴"

        card_title = f"{badge} Slot: **{slot_id}** | Cima: `{curr_line}` | Usura: **{line_wear}%**"
        
        with st.expander(card_title, expanded=True):
            c_sel, c_info, c_inspect = st.columns([2.5, 2, 1.5])

            with c_sel:
                line_idx = available_lines.index(curr_line) if curr_line in available_lines else 0
                selected_line = st.selectbox(
                    f"Seleziona Cima per {slot_id}",
                    available_lines,
                    index=line_idx,
                    key=f"select_line_{station_sel}_{idx}"
                )

                if selected_line != curr_line:
                    slots_df.loc[idx, "assigned_line"] = selected_line
                    has_changes = True
                    if selected_line != "Nessuna":
                        clean_sel_id = selected_line.split(" ")[0]
                        slot_type_desc = "Winch (Drum Winch)" if comp_type == "WINCH" else "Cesta (Basket / Rope Locker)"
                        assign_line_to_slot(clean_sel_id, st_code, slot_type_desc, slot_id)

            with c_info:
                st.write("**Stato Cima**")
                if curr_line != "Nessuna":
                    st.caption(f"Stato: `{line_status}`")
                    st.progress(line_wear / 100)
                else:
                    st.caption("Nessuna cima montata su questo tamburo/cesta.")

            with c_inspect:
                st.write("**Ispezione Danno**")
                if curr_line != "Nessuna":
                    if st.button("📸 Ispeziona AI", key=f"btn_ai_{station_sel}_{idx}", use_container_width=True):
                        open_line_inspection_dialog(curr_line, line_wear)
                else:
                    st.button("📸 Ispeziona AI", key=f"btn_ai_dis_{station_sel}_{idx}", disabled=True, use_container_width=True)

    if has_changes:
        save_mooring_station_components(slots_df.to_dict(orient="records"), station_sel)
        st.toast("Assegnazione cime aggiornata!", icon="💾")
        st.rerun()

    # TABELLA RIASSUNTIVA DELLE CIME NELLA STAZIONE
    st.markdown("---")
    st.subheader("📋 Tabella Riassuntiva Cime Stazione")
    
    summary_data = []
    for _, r in slots_df.iterrows():
        l_name = r["assigned_line"]
        wear_val = 0
        st_val = "N/D"
        if l_name != "Nessuna" and not lines_history_df.empty:
            clean_id = l_name.split(" ")[0]
            id_col = "line_id" if "line_id" in lines_history_df.columns else "id"
            match = lines_history_df[lines_history_df[id_col].astype(str) == clean_id]
            if not match.empty:
                wear_val = int(match.iloc[0].get("wear_percentage", 0))
                st_val = str(match.iloc[0].get("status", "OTTIMO"))

        summary_data.append({
            "Posizione/Slot": r["slot_id"],
            "Tipologia Supporto": r["comp_type"],
            "Cima Assegnata": l_name,
            "Usura Cima (%)": wear_val,
            "Stato Cima": st_val
        })

    st.dataframe(pd.DataFrame(summary_data), use_container_width=True)
