"""Certificate register and engineering review UI.

Extracted PDF values are presented as unverified until the operator reviews and
accepts them. The original PDF is retained with SHA-256 provenance when saved.
No generic elastic modulus or MEG4 status is invented by the UI.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.pdf_parser import parse_line_certificate, parse_certificate_text
from database.db_manager import (
    save_certificate_to_db,
    load_certificates_from_db,
    save_lines_inventory_to_db,
    load_lines_inventory_from_db,
)
from database.certificate_repository import (
    save_reviewed_certificate,
    load_certificate_records,
    get_certificate_pdf,
)


def _positive(value: float) -> bool:
    return float(value) > 0.0


def render_tab_certificate():
    st.header("📜 Modulo Certificati Cavi")
    st.caption("Importazione PDF → parsing → revisione operatore → archivio tracciabile")

    col_left, col_right = st.columns([1, 1.2])

    with col_left:
        st.subheader("📤 Carica Documento")
        uploaded_file = st.file_uploader(
            "Trascina qui il file PDF del certificato",
            type=["pdf"],
            key="pdf_uploader",
        )
        pasted_text = st.text_area(
            "Oppure incolla il testo del certificato",
            height=160,
            key="pasted_text_area",
        )

        if st.button("🔍 Esegui Parsing Certificato", type="primary", use_container_width=True):
            if uploaded_file is not None:
                parsed = parse_line_certificate(uploaded_file)
                st.session_state["parsed_cert_pdf_bytes"] = uploaded_file.getvalue()
                st.session_state["parsed_cert_filename"] = uploaded_file.name
            else:
                parsed = parse_certificate_text(pasted_text)
                st.session_state["parsed_cert_pdf_bytes"] = None
                st.session_state["parsed_cert_filename"] = ""
            if parsed:
                st.session_state["parsed_cert_data"] = parsed
                st.success("Estrazione completata. I dati richiedono revisione prima del salvataggio.")
            else:
                st.error("Impossibile estrarre dati dal certificato.")

        cdata = st.session_state.get("parsed_cert_data", {})
        if cdata:
            for warning in cdata.get("_warnings", []):
                st.warning(warning)
            for error in cdata.get("_validation_errors", []):
                st.error(error)
            st.info("🔎 REVIEW REQUIRED — l'estrazione automatica non costituisce validazione del certificato.")
            if st.session_state.get("parsed_cert_pdf_bytes"):
                st.caption(f"Source PDF: {st.session_state.get('parsed_cert_filename', 'certificate.pdf')}")

    with col_right:
        st.subheader("📝 Dettagli Certificato")
        cdata = st.session_state.get("parsed_cert_data", {})

        with st.form("form_save_certificate_and_line"):
            c1, c2 = st.columns(2)
            with c1:
                cert_id = st.text_input("ID Certificato / Serial No.", value=str(cdata.get("cert_id", "")))
                manufacturer = st.text_input("Produttore Cavo", value=str(cdata.get("manufacturer", "")))
                material = st.text_input("Materiale / Grade", value=str(cdata.get("main_material", "")))
                diameter_mm = st.number_input("Diametro Cavo (mm)", min_value=0.0, value=float(cdata.get("main_diameter_mm", 0.0)), step=1.0)

            with c2:
                ldbf_tons = st.number_input("LDBF (ton-force)", min_value=0.0, value=float(cdata.get("ldbf_tons", 0.0)), step=0.1)
                ship_mbl_tons = st.number_input("Ship Design MBL (ton-force)", min_value=0.0, value=float(cdata.get("ship_design_mbl_tons", 0.0)), step=0.1)
                length_m = st.number_input("Lunghezza Cavo (m)", min_value=0.0, value=float(cdata.get("main_length_m", 0.0)), step=1.0)
                standard = st.text_input("Standard / Basis", value=str(cdata.get("standard", "")))

            st.divider()
            st.markdown("**📈 Average Immediate Strain**")
            strain = cdata.get("average_immediate_strain_pct", {})
            s_cols = st.columns(5)
            strain_values = {
                pct: col.number_input(
                    f"{pct}% LDBF", min_value=0.0,
                    value=float(strain.get(str(pct), 0.0)), step=0.01, format="%.4f"
                )
                for col, pct in zip(s_cols, (10, 20, 30, 40, 50))
            }

            st.divider()
            st.markdown("**🪢 Mooring Tail — dati separati**")
            has_tail = st.checkbox("Presenza Tail", value=bool(cdata.get("has_tail", False)))
            t1, t2, t3 = st.columns(3)
            tail_mat = t1.text_input("Materiale Tail", value=str(cdata.get("tail_material", "")), disabled=not has_tail)
            tail_len = t2.number_input("Tail Length (m)", min_value=0.0, value=float(cdata.get("tail_length_m", 0.0)), step=0.5, disabled=not has_tail)
            tail_mbl = t3.number_input("Tail TDBF (ton-force)", min_value=0.0, value=float(cdata.get("tail_mbl_tons", 0.0)), step=0.1, disabled=not has_tail)

            st.divider()
            lines_df = st.session_state.get("lines_inventory", pd.DataFrame())
            line_options = ["Nessuna (Salva solo Certificato)"]
            if not lines_df.empty and "line_name" in lines_df.columns:
                line_options += lines_df["line_name"].astype(str).tolist()
            selected_line_name = st.selectbox("Associa alla linea", line_options)
            winch_location = st.radio("Configurazione", ["Working Drum", "Storage Basket"], horizontal=True)
            accepted = st.checkbox("Confermo di aver verificato i valori contro il certificato originale.")
            btn_save = st.form_submit_button("💾 Salva Certificato", type="primary", use_container_width=True)

            if btn_save:
                errors = []
                if not cert_id.strip(): errors.append("Certificate ID is required.")
                if not manufacturer.strip(): errors.append("Manufacturer is required.")
                if not material.strip(): errors.append("Material/grade is required.")
                if not _positive(diameter_mm): errors.append("Diameter must be greater than zero.")
                if not _positive(ldbf_tons): errors.append("LDBF must be greater than zero.")
                if not _positive(length_m): errors.append("Line length must be greater than zero.")
                if has_tail and (not _positive(tail_len) or not _positive(tail_mbl) or not tail_mat.strip()):
                    errors.append("Tail material, length and TDBF are required when a tail is present.")
                if not accepted: errors.append("Manual certificate review must be confirmed before saving.")
                if errors:
                    for error in errors: st.error(error)
                else:
                    pdf_bytes = st.session_state.get("parsed_cert_pdf_bytes")
                    record = {
                        "cert_id": cert_id.strip(), "certificate_type": "MOORING_LINE",
                        "manufacturer": manufacturer.strip(), "material_grade": material.strip(),
                        "diameter_mm": float(diameter_mm), "length_m": float(length_m),
                        "ship_design_mbl_t": float(ship_mbl_tons) if ship_mbl_tons > 0 else None,
                        "ldbf_t": float(ldbf_tons), "tail_tdbf_t": float(tail_mbl) if has_tail else None,
                        "tail_length_m": float(tail_len) if has_tail else None,
                        "standard_basis": standard.strip(), "issue_date": "",
                        "strain": strain_values, "source_text": str(cdata.get("_source_text", "")),
                        "extraction_method": str(cdata.get("_extraction_method", "manual/review")),
                        "review_status": "OPERATOR_VERIFIED",
                        "source_pdf_bytes": pdf_bytes,
                        "source_pdf_filename": st.session_state.get("parsed_cert_filename", ""),
                    }
                    save_reviewed_certificate(record)
                    save_certificate_to_db({
                        "cert_id": cert_id.strip(), "manufacturer": manufacturer.strip(), "material": material.strip(),
                        "diameter_mm": diameter_mm, "mbl_tons": ldbf_tons, "length_m": length_m,
                        "standard": standard.strip(), "issue_date": "", "has_tail": "YES" if has_tail else "NO",
                        "tail_material": tail_mat.strip() if has_tail else "N/A", "tail_length": tail_len if has_tail else 0.0,
                        "tail_mbl": tail_mbl if has_tail else 0.0,
                    })
                    st.session_state.certificates_db = load_certificates_from_db()

                    if selected_line_name != "Nessuna (Salva solo Certificato)" and not lines_df.empty:
                        idx = lines_df[lines_df["line_name"].astype(str) == selected_line_name].index
                        if not idx.empty:
                            i = idx[0]
                            lines_df.at[i, "cert_id"] = cert_id.strip()
                            lines_df.at[i, "material"] = material.strip()
                            lines_df.at[i, "diameter_mm"] = diameter_mm
                            lines_df.at[i, "mbl_tons"] = ldbf_tons
                            lines_df.at[i, "length_m"] = length_m
                            lines_df.at[i, "winch_location"] = winch_location
                            lines_df.at[i, "tail_length_m"] = tail_len if has_tail else 0.0
                            lines_df.at[i, "tail_mbl_tons"] = tail_mbl if has_tail else 0.0
                            save_lines_inventory_to_db(lines_df)
                            st.session_state.lines_inventory = load_lines_inventory_from_db()
                    st.success(f"Certificato {cert_id} salvato, PDF archiviato e marcato OPERATOR_VERIFIED.")

    st.divider()
    st.subheader("📋 Registro Certificati")
    records = load_certificate_records()
    if records:
        display = pd.DataFrame(records)
        st.dataframe(display, use_container_width=True, hide_index=True)

        st.markdown("### 📎 Documento originale")
        cert_options = display["cert_id"].astype(str).tolist()
        selected_cert = st.selectbox("Seleziona certificato", cert_options, key="certificate_document_selector")
        document = get_certificate_pdf(selected_cert)
        if document and document.get("source_pdf_blob"):
            st.caption(
                f"File: {document.get('source_pdf_filename') or 'certificate.pdf'} | "
                f"SHA-256: {document.get('source_pdf_sha256', '')}"
            )
            st.download_button(
                "⬇️ Apri / scarica PDF originale",
                data=document["source_pdf_blob"],
                file_name=document.get("source_pdf_filename") or f"{selected_cert}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.caption("Nessun PDF originale archiviato per questo certificato.")
    else:
        st.caption("Nessun certificato revisionato presente nel database.")
