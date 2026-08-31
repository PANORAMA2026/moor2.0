"""
views/tab_certificate.py
Interfaccia gestione certificati con debug attivo delle eccezioni di parsing.
"""

import streamlit as st
import pandas as pd
import traceback
from utils.pdf_parser import parse_line_certificate, parse_certificate_text
from database.db_manager import save_certificate_to_db, load_certificates_from_db

def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
    st.caption("Caricamento & Parsing Certificato PDF Multi-Componente")

    col1, col2 = st.columns([1, 1])

    with col1:
        uploaded_file = st.file_uploader(
            "Trascina qui il file PDF del certificato",
            type=["pdf"],
            key="pdf_uploader"
        )
        
        pasted_text = st.text_area(
            "Oppure incolla qui il testo del certificato",
            height=180,
            key="pasted_text_area"
        )

        btn_parse = st.button("🔍 Esegui Parsing Certificato", type="primary", use_container_width=True)

    with col2:
        st.info("👉 Incolla il testo del certificato o carica un PDF a sinistra e premi Esegui Parsing Certificato per iniziare.")

    if btn_parse:
        with st.spinner("Parsing del certificato in corso..."):
            parsed_data = None
            
            try:
                if uploaded_file is not None:
                    # Esegue il parsing sul buffer PDF
                    parsed_data = parse_line_certificate(uploaded_file)
                elif pasted_text.strip():
                    # Esegue il parsing sul testo incollato
                    parsed_data = parse_certificate_text(pasted_text)
                else:
                    st.warning("Seleziona un file PDF o incolla del testo prima di eseguire il parsing.")
                    return

                if parsed_data:
                    st.success("✅ Parsing completato con successo!")
                    st.json(parsed_data)
                    
                    # Salvataggio nel Database
                    save_certificate_to_db(parsed_data)
                    st.session_state.certificates_db = load_certificates_from_db()
                else:
                    st.error("❌ Il parser ha restituito 'None'. Nessun dato estratto dal file.")

            except Exception as err:
                # STAMPA IL CODICE DI ERRORE REALE A SCHERMO
                st.error(f"💥 ERRORE CRITICO DI ESECUZIONE: {type(err).__name__}")
                st.code(f"Dettaglio Errore: {str(err)}")
                st.code(traceback.format_exc())

    st.divider()
    st.subheader("📋 Registro Certificati Salvati nel Database")
    
    if "certificates_db" in st.session_state and not st.session_state.certificates_db.empty:
        st.dataframe(st.session_state.certificates_db, use_container_width=True)
    else:
        st.caption("Nessun certificato presente nel database.")
