"""
views/tab_certificate.py
Vista per la gestione, caricamento e parsing dei certificati cavi multi-componente.
Identifica l'anello debole (Weak Point) e permette l'associazione diretta a Mooring Station, Winch Drum (Drum A / Drum B) e Basket.
"""

import pandas as pd
import streamlit as st
from database.db_manager import (
    load_certificates_from_db,
    save_certificate_to_db,
    assign_line_to_slot
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

    # VISUALIZZAZIONE COMPONENTI, WEAK POINT E ASSOCIAZIONE POSTAZIONE
    if "parsed_cert_temp" in st.session_state:
        cd = st.session_state["parsed_cert_temp"]

        # Calcolo anello debole (Weak Point)
        components = {
            "Main Line": cd.get("main_mbl_tons", 0.0),
        }
        if cd.get("has_geolink"):
            components["GeoLink Lashing"] = cd.get("geolink_mbl_tons", 0.0)
        if cd.get("has_tail"):
            components["Tail (Coda)"] = cd.get("tail_mbl_tons", 0.0)

        valid_components = {k: v for k, v in components.items() if v > 0}
        weak_point_name = min(valid_components, key=valid_components.get) if valid_components else "Main Line"
        weak_point_mbl = valid_components.get(weak_point_name, 0.0)
        limite_55_mbl = round(weak_point_mbl * 0.55, 2)

        with col_res:
            st.markdown("### 📋 Dati Estratti dal Certificato")
            st.caption(
                f"**ID Certificato:** `{cd.get('cert_id')}` | **Produttore:**"
                f" {cd.get('manufacturer')}"
            )

            # Scomposizione 3 parti
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

            # Box Weak Point
            st.warning(
                f"⚠️ **WEAK POINT IDENTIFICATO:** **{weak_point_name}**\n\n"
                f"• **MBL Minimo Assieme:** **{weak_point_mbl:.2f} t**\n\n"
                f"• **Limite Operativo MEG4 (55% MBL):** **{limite_55_mbl:.2f} t**\n\n"
                f"*Valore di calcolo per le tensioni d'ormeggio.*"
            )

            # ASSOCIAZIONE MOORING STATION / WINCH / BASKET / DRUMS
            st.markdown("#### ⚓ Assegnazione Postazione d'Ormeggio & Tamburo Winch")
            col_a, col_b, col_c, col_d = st.columns([1, 1, 0.8, 1])

            with col_a:
                station = st.selectbox(
                    "Mooring Station",
                    [
                        "FWD (Prora)",
                        "AFT (Poppa)",
                        "MID FWD (Centro Prora)",
                        "MID AFT (Centro Poppa)",
                    ],
                    key="sel_station",
                )

            with col_b:
                winch_name = st.selectbox(
                    "Winch",
                    [
                        "Winch 1",
                        "Winch 2",
                        "Winch 3",
                        "Winch 4",
                        "Winch 5",
                        "Winch 6",
                    ],
                    key="sel_winch",
                )

            with col_c:
                winch_drum = st.selectbox(
                    "Tamburo",
                    ["Drum A", "Drum B", "Capstan", "Storage Reel"],
                    key="sel_drum",
                )

            with col_d:
                basket_id = st.text_input(
                    "Basket / Line ID", value="G1-GT1 FWD", key="sel_basket"
                )

            if st.button("💾 Salva & Associa Certificato", type="primary"):
                record = {
                    "cert_id": cd.get("cert_id", "CERT-UNKNOWN"),
                    "line_id": basket_id if basket_id else "G1-GT1 FWD",
                    "station": station,
                    "assigned_slot": winch_name,
                    "storage_type": "Winch",
                    "winch_drum": winch_drum,
                    "manufacturer": cd.get("manufacturer", "N/D"),
                    "material": cd.get("main_material", "HMPE"),
                    "diameter_mm": cd.get("main_diameter_mm", 0.0),
                    "length_m": cd.get("main_length_m", 220.0),
                    "mbl_tons": weak_point_mbl,
                    "mbl_55_limit": limite_55_mbl,
                    "weak_point": weak_point_name,
                    "has_geolink": "YES" if cd.get("has_geolink") else "NO",
                    "geolink_mbl": cd.get("geolink_mbl_tons", 0.0),
                    "has_tail": "YES" if cd.get("has_tail") else "NO",
                    "tail_material": cd.get("tail_material", "N/A"),
                    "tail_diameter": cd.get("tail_diameter_mm", 0.0),
                    "tail_mbl": cd.get("tail_mbl_tons", 0.0),
                    "tail_length": cd.get("tail_length_m", 0.0),
                    "standard": cd.get("standard", "MEG4"),
                    "issue_date": cd.get("issue_date", "2026-01-01"),
                }
                
                save_certificate_to_db(record)
                assign_line_to_slot(record["cert_id"], station, "Winch", winch_name, winch_drum)
                st.session_state.certificates_db = load_certificates_from_db()
                st.success(
                    f"✅ Cavo {basket_id} associato a {station} - {winch_name} [{winch_drum}]! MBL"
                    f" operativo: {weak_point_mbl:.2f} t (Limite 55%:"
                    f" {limite_55_mbl:.2f} t)."
                )

    st.divider()

    # REGISTRO CERTIFICATI E ASSEGNAZIONI
    st.subheader("📚 Registro Cavi & Assegnazioni Salvate")
    df_certs = load_certificates_from_db()
    if not df_certs.empty:
        st.dataframe(df_certs, use_container_width=True)
    else:
        st.info("Nessun cavo o certificato presente nel database.")
