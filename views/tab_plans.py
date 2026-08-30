"""
views/tab_plans.py
Pianetti Mooring Station: Visualizzazione d'orientamento, Ispezione AI e Tabella Riassuntiva Persistente.
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
    save_station_image_file,
    get_station_image_path,
    save_line_history,
    load_certificates_from_db
)

# -----------------------------------------------------------------------------
# REFERENCE LIBRARY ISO 2307 / CI 2001
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
# CARICAMENTO DB
# -----------------------------------------------------------------------------
def load_station_data_from_db(station_name: str) -> pd.DataFrame:
    """Carica i componenti salvati nel DB e gestisce le chiavi mancanti."""
    db_data = get_mooring_station_components(station_name)
    records = []

    if isinstance(db_data, pd.DataFrame) and not db_data.empty:
        records = db_data.to_dict(orient="records")
    elif isinstance(db_data, list) and len(db_data) > 0:
        records = db_data

    clean_records = []
    for r in records:
        clean_records.append({
            "comp_type": r.get("comp_type", r.get("type", r.get("component_type", "WINCH"))),
            "comp_id": r.get("comp_id", r.get("id", r.get("component_id", "ELEMENTO"))),
            "pos_x": float(r.get("pos_x", r.get("x", r.get("x_pos", 0)))),
            "pos_y": float(r.get("pos_y", r.get("y", r.get("y_pos", 0)))),
            "line_drum_a": r.get("line_drum_a", "Nessuna"),
            "line_drum_b": r.get("line_drum_b", "Nessuna"),
            "line_capstan": r.get("line_capstan", "Nessuna"),
            "assigned_line_id": r.get("assigned_line_id", "N/D"),
            "source_basket": r.get("source_basket", "Nessuno"),
            "wear_pct": int(r.get("wear_pct", 0)),
            "condition": r.get("condition", "BUONO"),
            "last_inspection_date": r.get("last_inspection_date", str(date.today())),
            "last_inspection_note": r.get("last_inspection_note", "")
        })

    cols = ["comp_type", "comp_id", "pos_x", "pos_y", "line_drum_a", "line_drum_b", "line_capstan", "assigned_line_id", "source_basket", "wear_pct", "condition", "last_inspection_date", "last_inspection_note"]
    if clean_records:
        return pd.DataFrame(clean_records)
    return pd.DataFrame(columns=cols)


def update_line_inventory_and_history(line_name: str, new_wear: int, condition: str, note: str):
    """Sincronizza permanentemente con l'inventario generale e lo storico cime."""
    if not line_name or line_name == "Nessuna":
        return
    
    clean_line_id = line_name.split(" ")[0]
    lines_df = get_line_history()
    
    id_col = "line_id" if "line_id" in lines_df.columns else "id"
    if not lines_df.empty and clean_line_id in lines_df[id_col].astype(str).values:
        lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "wear_percentage"] = new_wear
        lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "status"] = condition
        lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "last_inspection"] = str(date.today())
        lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "notes"] = note
    else:
        new_row = pd.DataFrame([{
            "line_id": clean_line_id,
            "last_port": "N/D",
            "current_setup": "N/D",
            "applied_tension_mbl_pct": 0.0,
            "total_hours": 0.0,
            "accumulated_stress_index": 0.0,
            "wear_percentage": new_wear,
            "status": condition,
            "last_inspection": str(date.today()),
            "notes": note,
            "last_auto_sync": str(date.today())
        }])
        lines_df = pd.concat([lines_df, new_row], ignore_index=True)

    save_line_history(lines_df)


@st.dialog("📸 Analisi Foto Danno Cima (AI + Reference Library)", width="large")
def open_ai_inspection_dialog(row, idx, station_sel, st_df):
    st.write(f"Ispezione rapida: **{row.get('comp_id')}** — Cima: `{row.get('line_drum_a', 'Nessuna')}`")
    
    img_file = st.camera_input("Scatta foto al danno sulla cima")
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
            st.caption("📷 Foto Scattata a Bordo")
            st.image(Image.open(img_file), use_container_width=True)
        with col_ref:
            st.caption(f"📚 Catalogo Ufficiale ISO: **{ai_res['damage_type']}**")
            if ref_data["image_path"] and os.path.exists(ref_data["image_path"]):
                st.image(Image.open(ref_data["image_path"]), use_container_width=True)
            else:
                st.info(f"**Descrizione:** {ref_data['description']}\n\n**Gravità ISO:** `{ref_data['iso_severity']}`")

        st.markdown("---")
        st.write("**Conferma o Correggi Valutazione Usura Extra:**")
        
        if f"selected_wear_{idx}" not in st.session_state:
            st.session_state[f"selected_wear_{idx}"] = ai_res["suggested_extra_wear"]

        c_low, c_ai, c_high = st.columns(3)
        if c_low.button("📉 Lieve (+15%)"):
            st.session_state[f"selected_wear_{idx}"] = 15
        if c_ai.button(f"🤖 AI Default (+{ai_res['suggested_extra_wear']}%)"):
            st.session_state[f"selected_wear_{idx}"] = ai_res["suggested_extra_wear"]
        if c_high.button("📈 Severo (+45%)"):
            st.session_state[f"selected_wear_{idx}"] = 45

        final_extra = st.session_state[f"selected_wear_{idx}"]
        current_wear = int(row.get("wear_pct", 0))
        new_total_wear = min(100, current_wear + final_extra)

        st.metric("Usura Totale Calcolata", f"{new_total_wear}%", delta=f"+{final_extra}% applicati")

        if st.button("💾 Conferma ed Aggiorna Tutti i Tab", type="primary", use_container_width=True):
            st_df.loc[idx, "wear_pct"] = new_total_wear
            st_df.loc[idx, "condition"] = "DANNEGGIATO" if new_total_wear > 60 else "USURATO"
            st_df.loc[idx, "last_inspection_date"] = str(date.today())
            st_df.loc[idx, "last_inspection_note"] = f"AI Danno: {ai_res['damage_type']} (+{final_extra}%)"

            # 1. Salvataggio Stazione d'Ormeggio DB
            st.session_state.mooring_stations[station_sel] = st_df
            save_mooring_station_components(st_df.to_dict(orient="records"), station_sel)
            
            # 2. Sincronizzazione permanente su Inventario e Storico Cime DB
            target_line = row.get("line_drum_a", row.get("assigned_line_id", "Nessuna"))
            update_line_inventory_and_history(
                target_line, new_total_wear, str(st_df.loc[idx, "condition"]), str(st_df.loc[idx, "last_inspection_note"])
            )

            del st.session_state[f"selected_wear_{idx}"]
            st.success("Dati salvati permanentemente in memoria e registrati in tutti i Tab!")
            st.rerun()

# -----------------------------------------------------------------------------
# MAIN TAB PLANS
# -----------------------------------------------------------------------------
def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio")

    stations_list = [
        "Prua (Forward Station)",
        "Poppa (Aft Station)",
        "Centro Prua (Mid FWD)",
        "Centro Poppa (Mid AFT)"
    ]

    if "mooring_stations" not in st.session_state:
        st.session_state.mooring_stations = {}

    station_sel = st.selectbox("Seleziona Stazione d'Ormeggio", stations_list, key="selected_mooring_station")
    if not station_sel:
        return

    st_df = load_station_data_from_db(station_sel)
    st.session_state.mooring_stations[station_sel] = st_df

    # CARICAMENTO E VISUALIZZAZIONE IMMAGINE VISIVA
    saved_img_path = get_station_image_path(station_sel)

    uploaded_image = st.file_uploader(
        f"📷 Carica/Sostituisci Immagine di Orientamento per: {station_sel}",
        type=["png", "jpg", "jpeg"],
        key=f"uploader_{station_sel}"
    )

    if uploaded_image is not None:
        file_bytes = uploaded_image.getvalue()
        _, ext = os.path.splitext(uploaded_image.name)
        saved_img_path = save_station_image_file(station_sel, file_bytes, ext)
        st.success("Immagine di orientamento salvata!")
        st.rerun()

    if saved_img_path and os.path.exists(saved_img_path):
        raw_img = Image.open(saved_img_path)
        st.image(raw_img, caption=f"Orientamento Visivo — {station_sel}", width=500)
    else:
        st.info("ℹ️ Nessuna immagine caricata per questa stazione. Carica un file sopra per orientamento visivo.")

    # ISPEZIONE RAPIDA
    st.markdown("---")
    st.subheader(f"🛡️ Ispezione Rapida & Controllo Stato: {station_sel}")

    col_banner, col_confirm_all = st.columns([3, 1.2])
    with col_banner:
        st.info("ℹ️ Premi **'Conferma Tutti OK'** per registrare l'ispezione standard senza problemi.")
    with col_confirm_all:
        if st.button("✅ Conferma Tutti OK", type="primary", use_container_width=True, key=f"btn_ok_all_{station_sel}"):
            today_str = str(date.today())
            for idx in st_df.index:
                st_df.loc[idx, "last_inspection_date"] = today_str
                target_line = st_df.loc[idx, "line_drum_a"]
                update_line_inventory_and_history(
                    target_line, int(st_df.loc[idx, "wear_pct"]), str(st_df.loc[idx, "condition"]), "Ispezione Standard OK"
                )
            
            st.session_state.mooring_stations[station_sel] = st_df
            save_mooring_station_components(st_df.to_dict(orient="records"), station_sel)
            st.success("Ispezione salvata su DB!")
            st.rerun()

    st.caption("Segnala anomalie visive con foto solo sui cavi interessati:")
    for idx, row in st_df.iterrows():
        c_id, c_type, c_wear, c_action = st.columns([2, 2, 2.5, 1.5])
        wear = int(row.get("wear_pct", 0))
        badge = "🟢" if wear < 40 else "🟡" if wear < 70 else "🔴"
        
        c_id.write(f"**{row.get('comp_id', row.get('component_id', ''))}**")
        c_type.write(f"{row.get('comp_type', row.get('component_type', ''))} (`{row.get('line_drum_a', 'Nessuna')}`)")
        c_wear.write(f"{badge} Usura: **{wear}%** | {row.get('condition', 'OK')}")

        if c_action.button("📸 Segnala Danno", key=f"btn_ai_{station_sel}_{idx}"):
            open_ai_inspection_dialog(row, idx, station_sel, st_df)

    # MODIFICA TABELLARE CON SALVATAGGIO
    st.markdown("---")
    st.subheader(f"⚙️ Modifica Tabellare: {station_sel}")
    edited_df = st.data_editor(
        st_df, num_rows="dynamic", use_container_width=True, key=f"editor_{station_sel}"
    )

    if st.button("💾 Sincronizza Tabella su DB", key=f"btn_sync_editor_{station_sel}"):
        if not edited_df.empty:
            if "pos_x" in edited_df.columns:
                edited_df["pos_x"] = pd.to_numeric(edited_df["pos_x"], errors="coerce").fillna(0.0)
            if "pos_y" in edited_df.columns:
                edited_df["pos_y"] = pd.to_numeric(edited_df["pos_y"], errors="coerce").fillna(0.0)
            if "wear_pct" in edited_df.columns:
                edited_df["wear_pct"] = pd.to_numeric(edited_df["wear_pct"], errors="coerce").fillna(0).astype(int)

        st.session_state.mooring_stations[station_sel] = edited_df
        save_mooring_station_components(edited_df.to_dict(orient="records"), station_sel)
        st.success("Salvataggio DB eseguito!")
        st.rerun()
