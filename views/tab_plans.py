"""
views/tab_plans.py
Pianetti Mooring Station con caricamento immagine corretto, persistenza DB,
gestione eliminazione elementi e Ispezione Ibrida AI-Assisted integrata.
"""

import os
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from datetime import date
from streamlit_image_coordinates import streamlit_image_coordinates

from database.db_manager import (
    get_line_history,
    save_mooring_station_components,
    get_mooring_station_components,
    save_station_image_file,
    get_station_image_path,
    save_line_history,  # Sincronizzazione con Inventario/Storico
)

# -----------------------------------------------------------------------------
# REFERENCE LIBRARY PER ISPEZIONE AI (ISO 2307 / CI 2001)
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


def draw_components_on_image(image: Image.Image, components_df: pd.DataFrame) -> Image.Image:
    """Disegna marcatori ed etichette dettagliate con ID delle cime reali dell'inventario."""
    img_copy = image.copy().convert("RGB")
    draw = ImageDraw.Draw(img_copy)

    color_map = {
        "WINCH": (255, 75, 75),       # Rosso
        "BASKET": (255, 165, 0),     # Arancione
        "CHOCK": (0, 200, 83),       # Verde
        "CAPSTAN": (153, 50, 204)    # Viola
    }
    marker_size = 8

    try:
        font = ImageFont.truetype("arial.ttf", 11)
    except IOError:
        font = ImageFont.load_default()

    for _, row in components_df.iterrows():
        x = float(row.get("pos_x", 0))
        y = float(row.get("pos_y", 0))
        c_type = str(row.get("comp_type", "WINCH"))
        c_id = str(row.get("comp_id", ""))

        color = color_map.get(c_type, (0, 123, 255))

        # 1. Marcatore
        draw.rectangle(
            [x - marker_size, y - marker_size, x + marker_size, y + marker_size],
            fill=color, outline=(255, 255, 255), width=2
        )

        # 2. Formattazione Etichetta con Cime Reali dell'Inventario
        line_info = ""
        if c_type == "WINCH":
            l1 = row.get("line_drum_a", "Nessuna")
            l2 = row.get("line_drum_b", "Nessuna")
            cap = row.get("line_capstan", "Nessuna")
            details = []
            if l1 and l1 != "Nessuna": details.append(f"DrA: {l1.split(' ')[0]}")
            if l2 and l2 != "Nessuna": details.append(f"DrB: {l2.split(' ')[0]}")
            if cap and cap != "Nessuna": details.append(f"Cap: {cap.split(' ')[0]}")
            if details:
                line_info = f" ({', '.join(details)})"
        elif c_type == "BASKET":
            assigned = row.get("assigned_line_id", "Nessuna")
            if assigned and assigned != "Nessuna":
                line_info = f" [{assigned.split(' ')[0]}]"

        label_text = f"{c_id}{line_info}"

        # 3. Badge ad Alta Visibilità
        bbox = draw.textbbox((0, 0), label_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        pad = 3
        text_x = x - (text_w / 2)
        text_y = y - marker_size - text_h - 6

        draw.rectangle(
            [text_x - pad, text_y - pad, text_x + text_w + pad, text_y + text_h + pad],
            fill=(255, 255, 255), outline=(0, 0, 0), width=1
        )
        draw.text((text_x, text_y), label_text, fill=(0, 0, 0), font=font)

    return img_copy


def load_station_data_from_db(station_name: str) -> pd.DataFrame:
    """Carica in modo sicuro i componenti salvati nel DB per una specifica stazione."""
    db_data = get_mooring_station_components(station_name)
    records = []

    if isinstance(db_data, pd.DataFrame) and not db_data.empty:
        for _, row in db_data.iterrows():
            records.append({
                "comp_type": row.get("type", row.get("component_type", row.get("comp_type", "WINCH"))),
                "comp_id": row.get("id", row.get("component_id", row.get("comp_id", ""))),
                "pos_x": float(row.get("x", row.get("x_pos", row.get("pos_x", 0)))),
                "pos_y": float(row.get("y", row.get("y_pos", row.get("pos_y", 0)))),
                "line_drum_a": row.get("line_drum_a", "Nessuna"),
                "line_drum_b": row.get("line_drum_b", "Nessuna"),
                "line_capstan": row.get("line_capstan", "Nessuna"),
                "assigned_line_id": row.get("assigned_line_id", "N/D"),
                "source_basket": row.get("source_basket", "Nessuno"),
                "wear_pct": int(row.get("wear_pct", 0)),
                "condition": row.get("condition", "BUONO"),
                "last_inspection_date": row.get("last_inspection_date", str(date.today())),
                "last_inspection_note": row.get("last_inspection_note", "")
            })
    elif isinstance(db_data, list) and len(db_data) > 0:
        for row in db_data:
            records.append({
                "comp_type": row.get("type", row.get("component_type", row.get("comp_type", "WINCH"))),
                "comp_id": row.get("id", row.get("component_id", row.get("comp_id", ""))),
                "pos_x": float(row.get("x", row.get("x_pos", row.get("pos_x", 0)))),
                "pos_y": float(row.get("y", row.get("y_pos", row.get("pos_y", 0)))),
                "line_drum_a": row.get("line_drum_a", "Nessuna"),
                "line_drum_b": row.get("line_drum_b", "Nessuna"),
                "line_capstan": row.get("line_capstan", "Nessuna"),
                "assigned_line_id": row.get("assigned_line_id", "N/D"),
                "source_basket": row.get("source_basket", "Nessuno"),
                "wear_pct": int(row.get("wear_pct", 0)),
                "condition": row.get("condition", "BUONO"),
                "last_inspection_date": row.get("last_inspection_date", str(date.today())),
                "last_inspection_note": row.get("last_inspection_note", "")
            })

    if records:
        return pd.DataFrame(records)
    return pd.DataFrame(
        columns=["comp_type", "comp_id", "pos_x", "pos_y", "line_drum_a", "line_drum_b", "line_capstan", "assigned_line_id", "source_basket", "wear_pct", "condition", "last_inspection_date", "last_inspection_note"]
    )


def update_line_inventory_and_history(line_name: str, new_wear: int, condition: str, note: str):
    """Sincronizza permanentemente lo stato dell'ispezione con l'inventario generale cime su DB."""
    if not line_name or line_name == "Nessuna":
        return
    
    clean_line_id = line_name.split(" ")[0]
    lines_df = get_line_history()
    
    if not lines_df.empty:
        id_col = "line_id" if "line_id" in lines_df.columns else "id"
        if clean_line_id in lines_df[id_col].astype(str).values:
            lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "wear_percentage"] = new_wear
            lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "status"] = condition
            lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "last_inspection"] = str(date.today())
            lines_df.loc[lines_df[id_col].astype(str) == clean_line_id, "notes"] = note
            
            # Salvataggio su database
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
                target_line, new_total_wear, st_df.loc[idx, "condition"], st_df.loc[idx, "last_inspection_note"]
            )

            del st.session_state[f"selected_wear_{idx}"]
            st.success("Dati salvati permanentemente in memoria e registrati in tutti i Tab!")
            st.rerun()


def render_tab_plans():
    st.header("🏗️ Mappatura Stazioni d'Ormeggio & Pianetti Interattivi")

    # 1. CARICAMENTO STATO E DB (PERSISTENZA GARANTITA ALL'AVVIO APPLICAZIONE)
    if "mooring_stations" not in st.session_state:
        st.session_state.mooring_stations = {}

    stations_list = ["Prua (Forward Station)", "Poppa (Aft Station)"]
    for stat in stations_list:
        if stat not in st.session_state.mooring_stations:
            st.session_state.mooring_stations[stat] = load_station_data_from_db(stat)

    station_sel = st.selectbox(
        "Seleziona Stazione d'Ormeggio",
        stations_list,
    )
    if not station_sel:
        return

    st_df = st.session_state.mooring_stations[station_sel]

    # 2. RECUPERO CIME DALL'INVENTARIO DI BORDO
    lines_df = get_line_history()
    line_options = ["Nessuna"]
    
    if not lines_df.empty:
        for _, l_row in lines_df.iterrows():
            l_id = str(l_row.get("line_id", l_row.get("id", "Cima")))
            l_mat = str(l_row.get("material", l_row.get("type", "")))
            l_dia = str(l_row.get("diameter", ""))
            
            desc = f"{l_id}"
            if l_mat and l_mat != "nan":
                desc += f" ({l_mat}"
                if l_dia and l_dia != "nan":
                    desc += f" - {l_dia}mm"
                desc += ")"
            line_options.append(desc)

    # 3. CARICAMENTO IMMAGINE PIANETTO
    saved_img_path = get_station_image_path(station_sel)

    uploaded_image = st.file_uploader(
        f"📷 Carica/Sostituisci Pianetta per: {station_sel}",
        type=["png", "jpg", "jpeg"],
        key=f"uploader_{station_sel}"
    )

    if uploaded_image is not None:
        file_bytes = uploaded_image.getvalue()
        _, ext = os.path.splitext(uploaded_image.name)
        saved_img_path = save_station_image_file(station_sel, file_bytes, ext)
        st.success("Immagine caricata e registrata con successo!")
        st.rerun()

    if saved_img_path and os.path.exists(saved_img_path):
        raw_img = Image.open(saved_img_path)
    else:
        st.warning("⚠️ Nessun disegno caricato per questa stazione. Carica un file JPG/PNG sopra.")
        raw_img = Image.new('RGB', (650, 380), color=(240, 240, 240))

    TARGET_WIDTH = 650
    w_percent = TARGET_WIDTH / float(raw_img.size[0])
    target_height = int(float(raw_img.size[1]) * float(w_percent))
    bg_img = raw_img.resize((TARGET_WIDTH, target_height), Image.Resampling.LANCZOS)

    key_click = f"click_pos_{station_sel}"
    if key_click not in st.session_state:
        st.session_state[key_click] = {"x": int(TARGET_WIDTH / 2), "y": int(target_height / 2)}

    annotated_img = draw_components_on_image(bg_img, st_df)

    st.markdown("---")
    col_map, col_form = st.columns([1.7, 1.1])

    with col_map:
        st.subheader("👆 Clicca sul disegno per aggiungere un elemento")
        value = streamlit_image_coordinates(
            annotated_img,
            width=TARGET_WIDTH,
            key=f"img_coords_{station_sel}"
        )

        if value is not None:
            st.session_state[key_click] = {"x": value["x"], "y": value["y"]}

    with col_form:
        st.subheader("🎯 Configura Componente")
        curr_x = st.session_state[key_click]["x"]
        curr_y = st.session_state[key_click]["y"]
        st.info(f"Punto Cliccato: **X={curr_x} px, Y={curr_y} px**")

        comp_type = st.selectbox("Tipologia Elemento", ["WINCH", "BASKET", "CHOCK", "CAPSTAN"])
        comp_id = st.text_input("Identificativo Componente", f"{comp_type[0]}_{len(st_df)+1}")

        basket_options = ["Nessuno"] + st_df[st_df["comp_type"] == "BASKET"]["comp_id"].tolist()

        line_drum_a = "Nessuna"
        line_drum_b = "Nessuna"
        line_capstan = "Nessuna"
        assigned_line = "N/D"
        source_basket = "Nessuno"

        if comp_type == "WINCH":
            st.markdown("---")
            st.caption("⚙️ Assegnazione Cime dall'Inventario di Bordo")
            line_drum_a = st.selectbox("Cima - Tamburo A (Drum A)", line_options, key=f"dr_a_{station_sel}")
            line_drum_b = st.selectbox("Cima - Tamburo B (Drum B)", line_options, key=f"dr_b_{station_sel}")
            
            if st.checkbox("Collega cavo alla Capstan del Winch"):
                line_capstan = st.selectbox("Cima su Capstan", line_options, key=f"cap_{station_sel}")
                source_basket = st.selectbox("Origine Cima (Basket)", basket_options)

        elif comp_type == "BASKET":
            assigned_line = st.selectbox("Cima stivata nel Basket", line_options)

        elif comp_type == "CAPSTAN":
            line_capstan = st.selectbox("Cima d'Ormeggio collegata", line_options)
            source_basket = st.selectbox("Origine Cima (Basket)", basket_options)

        if st.button("➕ Salva ed Inserisci sul Pianetto", use_container_width=True, type="primary"):
            new_row = pd.DataFrame([{
                "comp_type": comp_type,
                "comp_id": comp_id,
                "pos_x": curr_x,
                "pos_y": curr_y,
                "line_drum_a": line_drum_a,
                "line_drum_b": line_drum_b,
                "line_capstan": line_capstan,
                "assigned_line_id": assigned_line if comp_type == "BASKET" else line_drum_a,
                "source_basket": source_basket,
                "wear_pct": 0,
                "condition": "OTTIMO",
                "last_inspection_date": str(date.today()),
                "last_inspection_note": "Inizializzazione"
            }])

            st_df = pd.concat([st_df, new_row], ignore_index=True)
            st.session_state.mooring_stations[station_sel] = st_df

            # Salvataggio immediato e persistente su DB SQLite
            db_components = st_df.to_dict(orient="records")
            save_mooring_station_components(db_components, station_sel)
            st.success(f"Elemento {comp_id} salvato permanentemente!")
            st.rerun()

    # -------------------------------------------------------------------------
    # ISPEZIONE IBRIDA RAPIDA (ZERO SFORZO + FOTO AI)
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.subheader(f"🛡️ Ispezione Rapida & Controllo Stato: {station_sel}")

    col_banner, col_confirm_all = st.columns([3, 1.2])
    with col_banner:
        st.info("ℹ️ **Procedura Standard:** Se non ci sono anomalie visive, premi **'Conferma Tutti OK'** per validare lo stato per tutti i componenti.")
    with col_confirm_all:
        if st.button("✅ Conferma Tutti OK", type="primary", use_container_width=True):
            today_str = str(date.today())
            for idx in st_df.index:
                st_df.loc[idx, "last_inspection_date"] = today_str
                # Sincronizzazione automatica con Inventario Cime DB
                target_line = st_df.loc[idx, "line_drum_a"]
                update_line_inventory_and_history(
                    target_line, int(st_df.loc[idx, "wear_pct"]), str(st_df.loc[idx, "condition"]), "Ispezione Standard OK"
                )
            
            st.session_state.mooring_stations[station_sel] = st_df
            save_mooring_station_components(st_df.to_dict(orient="records"), station_sel)
            st.success("Ispezione mensile confermata e registrata in memoria!")
            st.rerun()

    st.caption("Segnala anomalie visive con foto solo sui cavi interessati:")
    for idx, row in st_df.iterrows():
        c_id, c_type, c_wear, c_action = st.columns([2, 2, 2.5, 1.5])
        wear = int(row.get("wear_pct", 0))
        badge = "🟢" if wear < 40 else "🟡" if wear < 70 else "🔴"
        
        c_id.write(f"**{row.get('comp_id')}**")
        c_type.write(f"{row.get('comp_type')} (`{row.get('line_drum_a', 'Nessuna')}`)")
        c_wear.write(f"{badge} Usura: **{wear}%** | {row.get('condition', 'OK')}")

        if c_action.button("📸 Segnala Danno", key=f"btn_ai_{station_sel}_{idx}"):
            open_ai_inspection_dialog(row, idx, station_sel, st_df)

    # TABELLA E SINCRONIZZAZIONE DB
    st.markdown("---")
    st.subheader(f"⚙️ Configurazione Tabellare: {station_sel}")
    edited_df = st.data_editor(
        st_df, num_rows="dynamic", use_container_width=True, key=f"editor_{station_sel}"
    )

    if st.button("💾 Sincronizza Tutti i Dati su DB"):
        st.session_state.mooring_stations[station_sel] = edited_df
        db_components = edited_df.to_dict(orient="records")
        save_mooring_station_components(db_components, station_sel)
        st.success("Database aggiornato con successo!")
        st.rerun()

    # GESTIONE CANCELLAZIONE ELEMENTI CON SINCRONIZZAZIONE DB
    st.markdown("---")
    st.subheader(f"🗑️ Eliminazione Elementi: {station_sel}")

    if not st_df.empty:
        for idx, row in st_df.iterrows():
            c1, c2, c3, c4 = st.columns([1.5, 2, 3, 1])
            c1.write(f"**{row.get('comp_type', '')}**")
            c2.write(f"ID: `{row.get('comp_id', '')}`")
            c3.write(f"Posizione: ({int(row.get('pos_x', 0))}px, {int(row.get('pos_y', 0))}px)")
            
            if c4.button("🗑️", key=f"del_btn_{station_sel}_{idx}"):
                updated_df = st_df.drop(idx).reset_index(drop=True)
                st.session_state.mooring_stations[station_sel] = updated_df
                save_mooring_station_components(updated_df.to_dict(orient="records"), station_sel)
                st.success(f"Elemento {row.get('comp_id', '')} rimosso con successo dal DB!")
                st.rerun()

        st.caption("")
        if st.button(f"🗑️ Rimuovi Tutti gli Elementi di {station_sel}", type="secondary"):
            empty_df = pd.DataFrame(columns=st_df.columns)
            st.session_state.mooring_stations[station_sel] = empty_df
            save_mooring_station_components([], station_sel)
            st.success(f"Tutti gli elementi di {station_sel} sono stati eliminati dal DB!")
            st.rerun()
    else:
        st.info("Nessun elemento presente da poter cancellare in questa stazione.")
