"""
views/tab_certificate.py
Modulo Certificati Cavi: Parsing PDF, assegnazione slot e suddivisione esplicita FWD / AFT.
"""

import pandas as pd
import streamlit as st
from utils.pdf_parser import parse_line_certificate, parse_certificate_text
from database.db_manager import (
    load_certificates_from_db,
    save_certificate_to_db,
    save_line_history,
    assign_line_to_slot,
    get_mooring_station_components,
    save_mooring_station_components
)


def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")

    # 1. SEZIONE UPLOAD & PARSING
    st.subheader("📥 Caricamento & Parsing Certificato PDF")
    col_up, col_preview = st.columns([1, 1.5])

    with col_up:
        uploaded_file = st.file_uploader("Trascina qui il file PDF", type=["pdf"], key="cert_pdf_uploader")
        text_input = st.text_area("Oppure incolla qui il testo del certificato", height=100, key="cert_text_area")

        if st.button("🔍 Esegui Parsing Certificato", type="primary", use_container_width=True):
            extracted = None
            if uploaded_file is not None:
                extracted = parse_line_certificate(uploaded_file)
            elif text_input.strip():
                extracted = parse_certificate_text(text_input.strip())

            if extracted:
                st.session_state["active_parsed_cert"] = extracted
                st.success("Parsing completato!")
            else:
                st.error("⚠️ Nessun file o testo fornito.")

    with col_preview:
        if "active_parsed_cert" in st.session_state:
            ext = st.session_state["active_parsed_cert"]
            st.markdown("### 📋 Dati Estratti")
            st.write(f"**ID Certificato:** `{ext['cert_id']}` | **Produttore:** {ext['manufacturer']}")
            
            p_col1, p_col2 = st.columns(2)
            p_col1.metric("MBL Main Line", f"{ext['main_mbl_tons']} t")
            p_col1.metric("Diametro", f"{ext['main_diameter_mm']} mm")
            p_col2.metric("Materiale", ext['main_material'])
            p_col2.metric("Lunghezza", f"{ext['main_length_m']} m")

            if ext.get("has_geolink"):
                st.caption(f"🔗 **GeoLink:** MBL {ext['geolink_mbl_tons']} t")
            if ext.get("has_tail"):
                st.caption(f"🪢 **Tail:** {ext['tail_material']} | Ø {ext['tail_diameter_mm']} mm | MBL {ext['tail_mbl_tons']} t")

    st.markdown("---")

    # 2. SEZIONE ASSEGNAZIONE STAZIONE E SLOT
    if "active_parsed_cert" in st.session_state:
        ext = st.session_state["active_parsed_cert"]
        st.subheader("⚙️ Assegnazione Stazione & Slot")

        with st.form("form_assign_cert"):
            station_choice = st.radio(
                "Seleziona Stazione di Ormeggio:",
                ["Prua (Forward Station)", "Poppa (Aft Station)"],
                horizontal=True
            )
            station_code = "FWD" if "Prua" in station_choice else "AFT"

            col_a1, col_a2 = st.columns(2)

            station_comps = get_mooring_station_components(station_choice)
            winch_list = []
            basket_list = []
            
            if not station_comps.empty:
                w_df = station_comps[station_comps["component_type"] == "WINCH"]
                for _, w_row in w_df.iterrows():
                    c_id = w_row["component_id"]
                    winch_list.extend([f"{c_id} (Drum A)", f"{c_id} (Drum B)"])
                
                b_df = station_comps[station_comps["component_type"] == "BASKET"]
                basket_list = b_df["component_id"].tolist()

            if not winch_list:
                winch_list = [f"{station_code} Winch #{i} (Drum A)" for i in range(1, 7)] + [f"{station_code} Winch #{i} (Drum B)" for i in range(1, 7)]
            if not basket_list:
                basket_list = [f"{station_code} Basket #1", f"{station_code} Basket #2"]

            with col_a1:
                storage_type = st.selectbox(
                    "Tipo Alloggiamento:",
                    ["Winch (Drum Winch)", "Cesta (Basket / Rope Locker)", "Cavo di Riserva (Spare Line)"]
                )

            with col_a2:
                if "Winch" in storage_type:
                    target_slot = st.selectbox("Slot Winch Destinazione:", winch_list)
                elif "Cesta" in storage_type:
                    target_slot = st.selectbox("Basket Destinazione:", basket_list)
                else:
                    target_slot = f"{station_code} Spare Storage"

            if st.form_submit_button("💾 Salva Certificato nel DB", type="primary", use_container_width=True):
                cert_record = {
                    "cert_id": ext["cert_id"],
                    "manufacturer": ext["manufacturer"],
                    "material": ext["main_material"],
                    "diameter_mm": ext["main_diameter_mm"],
                    "mbl_tons": ext["main_mbl_tons"],
                    "length_m": ext["main_length_m"],
                    "station": station_code,
                    "assigned_slot": target_slot,
                    "storage_type": storage_type,
                    "has_geolink": "SI" if ext.get("has_geolink") else "NO",
                    "geolink_mbl": ext.get("geolink_mbl_tons", 0.0),
                    "has_tail": "SI" if ext.get("has_tail") else "NO",
                    "tail_material": ext.get("tail_material", "N/A"),
                    "tail_diameter": ext.get("tail_diameter_mm", 0.0),
                    "tail_mbl": ext.get("tail_mbl_tons", 0.0),
                    "tail_length": ext.get("tail_length_m", 0.0),
                    "standard": ext.get("standard", "MEG4"),
                    "issue_date": ""
                }
                
                save_certificate_to_db(cert_record)
                assign_line_to_slot(ext["cert_id"], station_code, storage_type, target_slot)

                if not station_comps.empty:
                    clean_comp_id = target_slot.split(" ")[0]
                    for idx, row in station_comps.iterrows():
                        if row["component_id"] == clean_comp_id:
                            if "(Drum A)" in target_slot:
                                station_comps.loc[idx, "line_drum_a"] = ext["cert_id"]
                            elif "(Drum B)" in target_slot:
                                station_comps.loc[idx, "line_drum_b"] = ext["cert_id"]
                            elif "Basket" in target_slot or "Cesta" in storage_type:
                                station_comps.loc[idx, "assigned_line_id"] = ext["cert_id"]
                    save_mooring_station_components(station_comps.to_dict(orient="records"), station_choice)

                line_entry = {
                    "line_id": ext["cert_id"],
                    "last_port": "Inizializzazione",
                    "current_setup": target_slot,
                    "applied_tension_mbl_pct": 0.0,
                    "total_hours": 0.0,
                    "accumulated_stress_index": 0.0,
                    "last_auto_sync": "Ora"
                }
                save_line_history(pd.DataFrame([line_entry]))

                st.success(f"Certificato {ext['cert_id']} salvato in stazione {station_code}!")
                del st.session_state["active_parsed_cert"]
                st.rerun()

    st.markdown("---")

    # 3. TABELLE DIVISE PER MOORING STATION PRUA E POPPA
    st.subheader("📊 Registri Certificati per Stazione d'Ormeggio")

    certs_df = load_certificates_from_db()

    # SECTION 1: PRUA (FWD)
    st.markdown("#### ⚓ Mooring Station PRUA (Forward Station - FWD)")
    if not certs_df.empty and "station" in certs_df.columns:
        fwd_df = certs_df[certs_df["station"] == "FWD"]
        if not fwd_df.empty:
            st.dataframe(fwd_df, use_container_width=True)
        else:
            st.info("Nessun certificato registrato per la stazione di Prua (FWD).")
    else:
        st.info("Nessun dato registrato nel DB.")

    st.markdown("---")

    # SECTION 2: POPPA (AFT)
    st.markdown("#### ⚓ Mooring Station POPPA (Aft Station - AFT)")
    if not certs_df.empty and "station" in certs_df.columns:
        aft_df = certs_df[certs_df["station"] == "AFT"]
        if not aft_df.empty:
            st.dataframe(aft_df, use_container_width=True)
        else:
            st.info("Nessun certificato registrato per la stazione di Poppa (AFT).")
    else:
        st.info("Nessun dato registrato nel DB.")
