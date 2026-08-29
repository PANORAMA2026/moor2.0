"""
views/tab_certificate.py
Interfaccia per il caricamento, parsing ed archiviazione permanente dei certificati PDF.
"""

import pandas as pd
import streamlit as st
from utils.pdf_parser import parse_line_certificate
from database.db_manager import (
    get_certificates_from_db,
    save_certificate_to_db,
    save_line_history
)

def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
    st.info("Carica un certificato in formato PDF per estrarre automaticamente i dati di Main Line, GeoLink e Tail.")

    col_upload, col_db = st.columns([1.2, 1.8])

    with col_upload:
        st.subheader("📥 Parsing Certificato PDF")
        uploaded_file = st.file_uploader("Seleziona o trascina qui il file PDF", type=["pdf"])
        
        text_input = st.text_area("Oppure incolla qui il testo del certificato", height=100)

        if st.button("🔍 Esegui Parsing Certificato", type="primary", use_container_width=True):
            extracted = None
            if uploaded_file is not None:
                extracted = parse_line_certificate(uploaded_file)
            elif text_input.strip():
                from utils.pdf_parser import parse_certificate_text
                extracted = parse_certificate_text(text_input.strip())

            if extracted:
                st.session_state["active_parsed_cert"] = extracted
                st.success("Analisi completata con successo!")
            else:
                st.error("⚠️ Nessun file caricato o testo presente!")

        # MOSTRA SCHEDA DETTAGLIATA E FORM DI REGISTRAZIONE PERMANENTE
        if "active_parsed_cert" in st.session_state:
            ext = st.session_state["active_parsed_cert"]
            st.markdown("---")
            st.markdown("### 📋 Revisione Dati Estratti")

            with st.form("save_cert_form"):
                cert_id = st.text_input("ID Certificato", value=ext["cert_id"])
                mfg = st.text_input("Produttore", value=ext["manufacturer"])
                
                st.markdown("**1. Main Line (Cavo Principale)**")
                c1, c2 = st.columns(2)
                m_mat = c1.text_input("Materiale Main", value=ext["main_material"])
                m_dia = c2.number_input("Ø Main (mm)", value=float(ext["main_diameter_mm"]))
                
                c3, c4 = st.columns(2)
                m_mbl = c3.number_input("MBL Main (Tons)", value=float(ext["main_mbl_tons"]))
                m_len = c4.number_input("Lunghezza Main (m)", value=float(ext["main_length_m"]))

                # Sub-Componente GeoLink
                has_gl = st.checkbox("Include GeoLink / Connettore", value=ext["has_geolink"])
                gl_mbl = ext["geolink_mbl_tons"]
                if has_gl:
                    gl_mbl = st.number_input("MBL GeoLink (Tons)", value=float(ext["geolink_mbl_tons"]))

                # Sub-Componente Tail
                has_tail = st.checkbox("Include Tail / Gazza", value=ext["has_tail"])
                t_mat, t_dia, t_mbl, t_len = ext["tail_material"], ext["tail_diameter_mm"], ext["tail_mbl_tons"], ext["tail_length_m"]
                if has_tail:
                    tc1, tc2 = st.columns(2)
                    t_mat = tc1.text_input("Materiale Tail", value=ext["tail_material"])
                    t_dia = tc2.number_input("Ø Tail (mm)", value=float(ext["tail_diameter_mm"]))
                    tc3, tc4 = st.columns(2)
                    t_mbl = tc3.number_input("MBL Tail (Tons)", value=float(ext["tail_mbl_tons"]))
                    t_len = tc4.number_input("Lunghezza Tail (m)", value=float(ext["tail_length_m"]))

                btn_confirm = st.form_submit_button("💾 Salva Permanentemente nel DB", use_container_width=True)

                if btn_confirm:
                    # Record Completo per DB
                    cert_record = {
                        "cert_id": cert_id,
                        "manufacturer": mfg,
                        "material": m_mat,
                        "diameter_mm": m_dia,
                        "mbl_tons": m_mbl,
                        "length_m": m_len,
                        "has_geolink": "SI" if has_gl else "NO",
                        "geolink_mbl": gl_mbl if has_gl else 0.0,
                        "has_tail": "SI" if has_tail else "NO",
                        "tail_material": t_mat if has_tail else "N/A",
                        "tail_diameter": t_dia if has_tail else 0.0,
                        "tail_mbl": t_mbl if has_tail else 0.0,
                        "tail_length": t_len if has_tail else 0.0,
                        "standard": ext["standard"]
                    }
                    
                    # 1. Salvataggio su DB SQLite
                    save_certificate_to_db(cert_record)

                    # 2. Registrazione nell'Inventario Cime Generale
                    line_entry = {
                        "line_id": cert_id,
                        "material": m_mat,
                        "diameter": m_dia,
                        "mbl": m_mbl,
                        "length": m_len,
                        "wear_percentage": 0,
                        "status": "NUOVO"
                    }
                    save_line_history(pd.DataFrame([line_entry]))

                    st.success(f"Certificato {cert_id} salvato permanentemente in memoria e registrato su DB!")
                    del st.session_state["active_parsed_cert"]
                    st.rerun()

    with col_db:
        st.subheader("📚 Database Certificati Registrati (Fisso su DB)")
        certs_df = get_certificates_from_db()

        if not certs_df.empty:
            st.dataframe(certs_df, use_container_width=True, height=500)
        else:
            st.info("Nessun certificato presente nel database locale. Carica un PDF a sinistra per iniziare.")
