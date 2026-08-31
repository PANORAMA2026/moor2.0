"""
utils/pdf_parser.py
Parser ultra-veloce ottimizzato per latenza minima con Gemini 3.6 Flash.
"""

import json
import os
import re
import streamlit as st

try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo vettoriale dal PDF in millisecondi."""
    if uploaded_file is None:
        return ""

    try:
        if hasattr(uploaded_file, "getvalue"):
            file_bytes = uploaded_file.getvalue()
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            file_bytes = uploaded_file.read()
        else:
            file_bytes = uploaded_file

        if HAS_PYMUPDF:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text("text") + "\n"
            doc.close()
            return text.strip()
    except Exception:
        pass

    return ""


def parse_line_certificate(uploaded_file) -> dict:
    """Parsing ad altissima velocità."""
    if uploaded_file is None:
        return None

    # Estrazione testo rapida
    text = extract_text_from_pdf(uploaded_file)

    if text:
        return parse_certificate_text(text)

    # Fallback per PDF Scansionati
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=90)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")

            prompt = 'Estrai dati certificato MEG4 in JSON: {"cert_id":"","manufacturer":"","main_material":"","main_diameter_mm":0.0,"main_mbl_tons":0.0,"main_length_m":0.0,"standard":"MEG4"}'

            response = model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": img_bytes}],
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 250
                }
            )

            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Vision: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Invia un payload minimo a Gemini per azzerare la latenza."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")

            # Prompt compatto e rigido
            prompt = f"""Estrai in JSON i dati di questo certificato cavi d'ormeggio MEG4:
{{
    "cert_id": "string",
    "manufacturer": "string",
    "standard": "MEG4",
    "main_material": "string",
    "main_diameter_mm": float,
    "main_mbl_tons": float,
    "main_length_m": float,
    "has_tail": false,
    "tail_material": "",
    "tail_diameter_mm": 0.0,
    "tail_mbl_tons": 0.0,
    "tail_length_m": 0.0
}}

Testo:
{text[:1500]}"""

            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 250
                }
            )
            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Fallback Regex per errore API: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback offline ultra-veloce."""
    data = {
        "cert_id": "UNKNOWN", "manufacturer": "N/A", "main_material": "N/A",
        "main_diameter_mm": 0.0, "main_mbl_tons": 0.0, "main_length_m": 0.0,
        "has_geolink": False, "geolink_mbl_tons": 0.0, "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0, "has_tail": False, "tail_material": "",
        "tail_diameter_mm": 0.0, "tail_mbl_tons": 0.0, "tail_length_m": 0.0, "standard": "MEG4"
    }

    cert_m = re.search(r"(?:Cert|Certificate|Nr|No)\.?\s*:?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
    if cert_m:
        data["cert_id"] = cert_m.group(1)

    dia_m = re.search(r"(\d+(?:\.\d+)?)\s*mm", text, re.IGNORECASE)
    if dia_m:
        data["main_diameter_mm"] = float(dia_m.group(1))

    mbl_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:kN|t|tons)", text, re.IGNORECASE)
    if mbl_m:
        data["main_mbl_tons"] = float(mbl_m.group(1))

    return data
