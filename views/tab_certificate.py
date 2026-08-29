"""
views/tab_certificate.py
Vista per la gestione, caricamente e parsing dei certificati cavi multi-componente.
Identifica e calcola automaticamente l'anello debole (Weak Point) per i calcoli di tensione.
"""

import pandas as pd
import streamlit as st
from database.db_manager import (
    load_certificates_from_db,
    save_certificate_to_db,
)
from utils.pdf_parser import parse_certificate_text, parse_line_certificate


def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi & Drag and Drop PDF")
    st.subheader("📥 Caricamento & Parsing Certificato PDF Multi-Componente")

    col_up, col_res = st.columns([1, 1.2])

    with col_up:
        uploaded_pdf = st.file_uploader(
            "Trascina qui il file PDF del certificato",
            type=["pdf"],
            key="cert_pdf_uploader",
        )
        manual_text = st.text_area(
            "Oppure incolla qui il testo del certificato",
            height=150,
            key="cert_text_manual",
        )

        parse_btn = st.button("🔍 Esegui Parsing Certificato", type="primary")

    if parse_btn:
        cert_data = None
        if uploaded_pdf is not None:
            cert_data = parse_line_certificate(uploaded_pdf)
        elif manual_text.strip():
            cert_data = parse_certificate_text(manual_text)

        if cert_data:
            st.session_state["parsed_cert_temp"] = cert_data
            st.success("✅ Parsing completato con successo!")

    # VISUALIZZAZIONE COMPLETA DEI COMPONENTI ED IDENTIFICAZIONE WEAK POINT
    if "parsed_cert_temp" in st.session_state:
        cd = st.session_state["parsed_cert_temp"]

        # Calcolo dell'anello debole (Weak Point)
        components = {
            "Main Line": cd.get("main_mbl_tons", 0.0),
        }
        if cd.get("has_geolink"):
            components["GeoLink Lashing"] = cd.get("geolink_mbl_tons", 0.0)
        if cd.get("has_tail"):
            components["Tail (Coda)"] = cd.get("tail_mbl_tons", 0.0)

        # Filtra valori validi e trova il minimo
        valid_components = {k: v for k, v in components.items() if v > 0}
        weak_point_name = min(valid_components, key=valid_components.get)
        weak_point_mbl = valid_components[weak_point_name]
        limite_55_mbl = round(weak_point_mbl * 0.55, 2)

        with col_res:
            st.markdown("### 📋 Dati Estratti dal Certificato")
            st.caption(
                f"**ID Certificato:** `{cd.get('cert_id')}` | **Produttore:**"
                f" {cd.get('manufacturer')}"
            )

            # Tabella di riepilogo delle 3 parti del cavo
            st.markdown("#### 🔗 Scomposizione Componenti Cavo")
            c1, c2, c3 = st.columns(3)

            with c1:
                st.info(
                    f"**Main Line**\n\n"
                    f"• MBL: **{cd.get('main_mbl_tons', 0.0):.1f} t**\n\n"
                    f"• Ø: {cd.get('main_diameter_mm', 0.0):.0f} mm\n\n"
                    f"• Lunghezza: {cd.get('main_length_m', 0.0):.0f} m\n\n"
                    f"• Mat: {cd.get('main_material', 'N/A')}"
                )

            with c2:
                if cd.get("has_geolink"):
                    st.info(
                        f"**GeoLink Lashing**\n\n"
                        f"• MBL: **{cd.get('geolink_mbl_tons', 0.0):.1f} t**\n\n"
                        f"• Ø: {cd.get('geolink_diameter_mm', 0.0):.0f} mm\n\n"
                        f"• Materiale: Dyneema SK78"
                    )
                else:
                    st.caption("GeoLink: Non Presente")

            with c3:
                if cd.get("has_tail"):
                    st.info(
                        f"**Tail (Coda)**\n\n"
                        f"• MBL: **{cd.get('tail_mbl_tons', 0.0):.1f} t**\n\n"
                        f"• Ø: {cd.get('tail_diameter_mm', 0.0):.0f} mm\n\n"
                        f"• Lunghezza: {cd.get('tail_length_m', 0.0):.0f} m\n\n"
                        f"• Mat: {cd.get('tail_material', 'N/A')}"
                    )
                else:
                    st.caption("Tail: Non Presente")

            # BOX WEAK POINT E LIMITE OPERATIVO 55% MEG4
            st.warning(
                f"⚠️ **WEAK POINT IDENTIFICATO:** **{weak_point_name}**\n\n"
                f"• **MBL Minimo Assieme:** **{weak_point_mbl:.2f} t**\n\n"
                f"• **Limite Operativo MEG4 (55% MBL):** **{limite_55_mbl:.2f} t**\n\n"
                f"*Questo è il valore critico che verrà utilizzato nei calcoli delle tensioni d'ormeggio.*"
            )

            if st.button("💾 Salva Certificato nel Database", type="primary"):
                record = {
                    "cert_id": cd.get("cert_id"),
                    "manufacturer": cd.get("manufacturer"),
                    "material": cd.get("main_material"),
                    "diameter_mm": cd.get("main_diameter_mm"),
                    "mbl_tons": weak_point_mbl,  # Salva il valore dell'anello debole per i calcoli
                    "standard": cd.get("standard"),
                    "issue_date": "2025-12-12",
                }
                save_certificate_to_db(record)
                st.session_state.certificates_db = load_certificates_from_db()
                st.success(
                    f"Certificato {cd.get('cert_id')} salvato! MBL operativo"
                    f" impostato a {weak_point_mbl:.2f} t."
                )

    st.divider()

    # REGISTRO CERTIFICATI IN MEMORIA
    st.subheader("📚 Registro Certificati Salvati")
    df_certs = load_certificates_from_db()
    if not df_certs.empty:
        st.dataframe(df_certs, use_container_width=True)
    else:
        st.info("Nessun certificato presente nel database.")
