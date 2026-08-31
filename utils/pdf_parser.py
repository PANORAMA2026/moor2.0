"""
utils/pdf_parser.py
Parser ad alta velocità ottimizzato per Gemini 3.6 Flash.
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

# Nome del modello richiesto dall'endpoint API
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
    """Estrae il testo vettoriale dal PDF via PyMuPDF."""
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
    """Parsing diretto con gestione ottimizzata di file vettoriali e scansionati."""
    if uploaded_file is None:
        return None

    # 1. Tentativo di estrazione testo rapida
    text = extract_text_from_pdf(uploaded_file)
    if text and len(text) > 40:
        return parse_certificate_text(text)

    # 2. Parsing visivo ultraleggero per PDF scansionati (es. E14 FWD.pdf)
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = extract_bytes_from_file(uploaded_file)
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            # Compressione a 70 DPI per un payload ridotto e risposta istantanea
            pix = page.get_pixmap(dpi=70)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel(MODEL_NAME)

            prompt = """
            Sei un ingegnere navale esperto di cavi d'ormeggio MEG4.
            Analizza questo certificato ed estrai i dati.
            Restituisci ESCLUSIVAMENTE un JSON valido senza blocchi markdown con questa struttura:
            {
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
            }
            """

            response = model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": img_bytes}],
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 300
                }
            )

            res_text = response.text.strip()
            if res_text.startswith("```json"):
                res_text = res_text.replace("```json", "").replace("```", "").strip()

            return json.loads(res_text)

        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Immagine: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Parsing da testo vettoriale."""
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
{text[:2000]}"""

            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                    "max_output_tokens": 300
                }
            )

            res_text = response.text.strip()
            if res_text.startswith("```json"):
                res_text = res_text.replace("```json", "").replace("```", "").strip()

            return json.loads(res_text)
        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Testo: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback offline."""
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
