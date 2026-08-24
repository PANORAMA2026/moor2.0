"""
views/tab_certificate.py
Interfaccia per il caricamento ed estrazione dati da certificati PDF cavi.
"""

import streamlit as st
from utils.pdf_parser import parse_line_certificate

def render_tab_certificate():
    st.header("2. Parsing Certificati Cavi")
    st.info("Carica un certificato in formato PDF per estrarre MBL e diametro tramite RegEx.")

    uploaded_file = st.file_uploader("Seleziona il certificato PDF", type=["pdf"])
    
    if uploaded_file is not None:
        extracted = parse_line_certificate(uploaded_file)
        
        st.success("Analisi del file completata!")
        col1, col2, col3 = st.columns(3)
        col1.metric("MBL Estratto", f"{extracted['mbl_tons'] or 'N/A'} t")
        col2.metric("Diametro Estratto", f"{extracted['diameter_mm'] or 'N/A'} mm")
        col3.metric("Produttore Rilevato", extracted['manufacturer'])
        
        target_line = st.selectbox("Assegna questi dati alla linea:", 
                                   [l['id'] for l in st.session_state.get('lines_data', [])])
        
        if st.button("Aggiorna Scheda Linea"):
            for line in st.session_state.get('lines_data', []):
                if line['id'] == target_line:
                    if extracted['mbl_tons']: line['mbl'] = extracted['mbl_tons']
                    if extracted['diameter_mm']: line['diameter'] = extracted['diameter_mm']
            st.success(f"Dati della linea {target_line} aggiornati con successo!")
