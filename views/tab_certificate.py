"""
views/tab_certificate.py
Modulo per l'estrazione dati da certificati PDF tramite Gemini API
e l'associazione immediata delle linee d'ormeggio ai verricelli di bordo.
"""

import streamlit as st
import pandas as pd
from utils.pdf_parser import parse_line_certificate, parse_certificate_text
from database.db_manager import (
    save_certificate_to_db,
    load_certificates_from_db,
    save_lines_inventory_to_db,
    load_lines_inventory_from_db,
)


def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
    st.caption("Caricamento, parsing istantaneo e associazione cavo alla stazione d'ormeggio")

    col_left, col_right = st.columns([1, 1.2])

    # -------------------------------------------------------------------------
    # COLONNA DI SINISTRA: UPLOAD PDF & TESTO
    # -------------------------------------------------------------------------
    with col_left:
        st.subheader("📤 Carica Documento")
        uploaded_file = st.file_uploader(
            "Trascina qui il file PDF del certificato",
            type=["pdf"],
            key="pdf_uploader",
        )

        pasted_text = st.text_area(
            "Oppure incolla qui il testo del certificato",
            height=160,
            key="pasted_text_area",
        )

        btn_parse = st.button(
            "🔍 Esegui Parsing Certificato",
            type="primary",
            use_container_width=True,
        )

        if btn_parse:
            with st.spinner("Parsing rapido in corso..."):
                parsed = None
                if uploaded_file is not None:
                    parsed = parse_line_certificate(uploaded_file)
                elif pasted_text.strip():
                    parsed = parse_certificate_text(pasted_text)
                else:
                    st.warning("Seleziona un file PDF o incolla del testo.")

                if parsed:
                    st.session_state["parsed_cert_data"] = parsed
                    st.success("✅ Parsing completato con successo!")
                else:
                    st.error("❌ Impossibile estrarre i dati dal certificato.")

    # -------------------------------------------------------------------------
    # COLONNA DI DESTRA: FORM RIEPILOGO, ASSEGNAZIONE WINCH E SALVATAGGIO
    # -------------------------------------------------------------------------
    with col_right:
        st.subheader("📝 Dettagli Certificato & Configurazione Cavo")

        # Recupera i dati estratti dal parsing o imposta un dizionario vuoto
        cdata = st.session_state.get("parsed_cert_data", {})

        with st.form("form_save_certificate_and_line"):
            c1, c2 = st.columns(2)
            with c1:
                cert_id = st.text_input(
                    "ID Certificato / Serial No.",
                    value=str(cdata.get("cert_id", "")),
                )
                manufacturer = st.text_input(
                    "Produttore Cavo",
                    value=str(cdata.get("manufacturer", "")),
                )
                material = st.text_input(
                    "Materiale Principale",
                    value=str(cdata.get("main_material", "")),
                )
                diameter_mm = st.number_input(
                    "Diametro Cavo (mm)",
                    value=float(cdata.get("main_diameter_mm", 0.0)),
                    step=1.0,
                )

            with c2:
                mbl_tons = st.number_input(
                    "MBL Cavo (Tonnellate)",
                    value=float(cdata.get("main_mbl_tons", 0.0)),
                    step=0.1,
                )
                length_m = st.number_input(
                    "Lunghezza Cavo (m)",
                    value=float(cdata.get("main_length_m", 0.0)),
                    step=5.0,
                )
                # Calcolo stima automatica Modulo Elastico E
                default_e = 15.0 if "POLY" in str(material).upper() else 120.0 if "HMPE" in str(material).upper() else 20.0
                e_modulus = st.number_input(
                    "Modulo Elastico E (GPa)",
                    value=default_e,
                    help="Tipico: HMPE ~120 GPa, Poliestere/Polipropilene ~10-20 GPa",
                )
                standard = st.text_input(
                    "Standard di Collaudo",
                    value=str(cdata.get("standard", "MEG4")),
                )

            st.divider()
            st.markdown("**⚙️ Associazione Verricello & Posizione sulla Nave**")

            # Recupero inventario cavi dal session state
            lines_df = st.session_state.get("lines_inventory", pd.DataFrame())
            
            line_options = ["Nessuna (Salva solo Certificato nel DB)"]
            if not lines_df.empty and "line_name" in lines_df.columns:
                line_options += lines_df["line_name"].tolist()

            selected_line_name = st.selectbox(
                "Assegna questo certificato/cavo al Verricello (Winch):",
                options=line_options,
            )

            winch_location = st.radio(
                "Configurazione Tamburo Verricello:",
                ["Working Drum (In Tensione)", "Storage Basket (Riserva)"],
                horizontal=True,
            )

            st.divider()
            st.markdown("**🪢 Dettagli Tail (Coda di Choc)**")
            t1, t2, t3 = st.columns(3)
            with t1:
                has_tail = st.checkbox("Presenza Tail", value=bool(cdata.get("has_tail", False)))
                tail_mat = st.text_input("Mat. Tail", value=str(cdata.get("tail_material", "Nylon")))
            with t2:
                tail_len = st.number_input("Lunghezza (m)", value=float(cdata.get("tail_length_m", 11.0) if has_tail else 0.0))
                tail_dia = st.number_input("Diametro (mm)", value=float(cdata.get("tail_diameter_mm", 0.0) if has_tail else 0.0))
            with t3:
                tail_mbl = st.number_input("MBL Tail (t)", value=float(cdata.get("tail_mbl_tons", 0.0) if has_tail else 0.0))
                tail_e = st.number_input("E Tail (GPa)", value=6.0 if has_tail else 0.0)

            btn_save = st.form_submit_button("💾 Salva Certificato e Aggiorna Inventario Cavi", type="primary", use_container_width=True)

            if btn_save:
                # 1. Salvataggio Certificato nel DB Registro
                cert_record = {
                    "cert_id": cert_id,
                    "manufacturer": manufacturer,
                    "material": material,
                    "diameter_mm": diameter_mm,
                    "mbl_tons": mbl_tons,
                    "standard": standard,
                    "issue_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
                }
                save_certificate_to_db(cert_record)
                st.session_state.certificates_db = load_certificates_from_db()

                # 2. Aggiornamento Inventario Cavi se associato a un Winch
                if selected_line_name != "Nessuna (Salva solo Certificato nel DB)" and not lines_df.empty:
                    idx = lines_df[lines_df["line_name"] == selected_line_name].index
                    if not idx.empty:
                        i = idx[0]
                        lines_df.at[i, "cert_id"] = cert_id
                        lines_df.at[i, "material"] = material
                        lines_df.at[i, "diameter_mm"] = diameter_mm
                        lines_df.at[i, "mbl_tons"] = mbl_tons
                        lines_df.at[i, "length_m"] = length_m
                        lines_df.at[i, "E_modulus_GPa"] = e_modulus
                        lines_df.at[i, "winch_location"] = winch_location
                        lines_df.at[i, "has_tail"] = has_tail
                        lines_df.at[i, "tail_length_m"] = tail_len
                        lines_df.at[i, "tail_diameter_mm"] = tail_dia
                        lines_df.at[i, "tail_mbl_tons"] = tail_mbl
                        lines_df.at[i, "tail_E_modulus_GPa"] = tail_e
                        
                        save_lines_inventory_to_db(lines_df)
                        st.session_state.lines_inventory = load_lines_inventory_from_db()
                        st.success(f"✅ Certificato {cert_id} associato con successo a **{selected_line_name}** ({winch_location})!")
                else:
                    st.success(f"✅ Certificato {cert_id} registrato nel Database!")

    # -------------------------------------------------------------------------
    # TABELLA REGISTRO CERTIFICATI SALVATI
    # -------------------------------------------------------------------------
    st.divider()
    st.subheader("📋 Registro Certificati Salvati nel Database")
    if "certificates_db" in st.session_state and not st.session_state.certificates_db.empty:
        st.dataframe(st.session_state.certificates_db, use_container_width=True)
    else:
        st.caption("Nessun certificato presente nel database.")
