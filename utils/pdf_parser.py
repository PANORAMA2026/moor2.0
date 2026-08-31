"""
utils/pdf_parser.py
Parser ultra-veloce per Gemini 3.6 Flash con gestione sicura dell'output JSON.
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

MODEL_NAME = "gemini-3.6-flash"


def extract_bytes_from_file(uploaded_file) -> bytes:
    """Estrae i byte in modo sicuro riposizionando il puntatore dello stream."""
    if uploaded_file is None:
        return b""
    try:
        if hasattr(uploaded_file, "getvalue"):
            return uploaded_file.getvalue()
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            data = uploaded_file.read()
            uploaded_file.seek(0)
            return data
    except Exception:
        pass
    return b""


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo vettoriale dal PDF via PyMuPDF in millisecondi."""
    file_bytes = extract_bytes_from_file(uploaded_file)
    if not file_bytes or not HAS_PYMUPDF:
        return ""

    text = ""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page in doc:
            t = page.get_text("text")
            if t:
                text += t + "\n"
        doc.close()
    except Exception:
        pass

    return text.strip()


def parse_line_certificate(uploaded_file) -> dict:
    """Parsing ad alta velocità per file vettoriali e scansionati."""
    if uploaded_file is None:
        return None

    # 1. Parsing da testo locale se presente
    text = extract_text_from_pdf(uploaded_file)
    if text and len(text) > 40:
        return parse_certificate_text(text)

    # 2. Vision per PDF scansionati
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = extract_bytes_from_file(uploaded_file)
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            # DPI ottimizzati a 90 per bilanciare leggibilità e velocità di trasmissione
            pix = page.get_pixmap(dpi=90)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel(MODEL_NAME)

            prompt = """
            Sei un ingegnere navale esperto di cavi d'ormeggio MEG4.
            Analizza questo certificato ed estrai i dati reali.
            Restituisci un oggetto JSON valido con questa struttura esatta:
            {
                "cert_id": "string",
                "manufacturer": "string",
                "standard": "MEG4",
                "main_material": "string",
                "main_diameter_mm": 0.0,
                "main_mbl_tons": 0.0,
                "main_length_m": 0.0,
                "has_tail": false,
                "tail_material": "",
                "tail_diameter_mm": 0.0,
                "tail_mbl_tons": 0.0,
                "tail_length_m": 0.0
            }
            """

            response = model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": img_bytes}],
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 1000
                }
            )

            return json.loads(response.text)

        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Immagine: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Parsing da testo vettoriale tramite Gemini 3.6 Flash."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel(MODEL_NAME)

            prompt = f"""Estrai in JSON i dati di questo certificato cavi d'ormeggio MEG4:
{{
    "cert_id": "string",
    "manufacturer": "string",
    "standard": "MEG4",
    "main_material": "string",
    "main_diameter_mm": 0.0,
    "main_mbl_tons": 0.0,
    "main_length_m": 0.0,
    "has_tail": false,
    "tail_material": "",
    "tail_diameter_mm": 0.0,
    "tail_mbl_tons": 0.0,
    "tail_length_m": 0.0
}}

Testo certificato:
{text[:2500]}"""

            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 1000
                }
            )

            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Testo: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback locale offline."""
    data = {
        "cert_id": "UNKNOWN", "manufacturer": "N/A", "main_material": "N/A",
        "main_diameter_mm": 0.0, "main_mbl_tons": 0.0, "main_length_m": 0.0,
        "has_geolink": False, "geolink_mbl_tons": 0.0, "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0, "has_tail": False, "tail_material": "",
        "tail_diameter_mm": 0.0, "tail_mbl_tons": 0.0, "tail_length_m": 0.0, "standard": "MEG4"
    }

    if not text:
        return data

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
