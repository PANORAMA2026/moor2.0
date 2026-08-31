"""
utils/pdf_parser.py
Parser ultra-robusto per certificati MEG4 con selezione automatica del modello.
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


def extract_bytes_from_file(uploaded_file) -> bytes:
    """Estrae i byte dallo stream di Streamlit azzerando il puntatore."""
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


def resolve_working_model():
    """Trova il primo modello attivo compatibile per la tua API Key."""
    try:
        available_models = genai.list_models()
        for m in available_models:
            if "generateContent" in m.supported_generation_methods:
                return m.name
    except Exception:
        pass
    return "models/gemini-1.5-flash"


def safe_extract_json(text_response: str) -> dict:
    """Estrae ed esegue il parsing del JSON prevenendo errori di sintassi."""
    if not text_response:
        return None

    cleaned = text_response.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
        cleaned = cleaned.replace("```", "").strip()

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except Exception:
            pass

    try:
        return json.loads(cleaned)
    except Exception:
        return None


def parse_line_certificate(uploaded_file) -> dict:
    """Parsing principale del certificato cavi MEG4."""
    if uploaded_file is None:
        return None

    # 1. Parsing da testo vettoriale se disponibile
    text = extract_text_from_pdf(uploaded_file)
    if text and len(text) > 40:
        parsed_data = parse_certificate_text(text)
        if parsed_data:
            return parsed_data

    # 2. Vision fallback per PDF scansionati
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = extract_bytes_from_file(uploaded_file)
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=90)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model_name = resolve_working_model()
            model = genai.GenerativeModel(model_name)

            prompt = (
                "Sei un ingegnere navale. Estrai i dati tecnici di questo certificato cavi d'ormeggio MEG4.\n"
                "Restituisci ESCLUSIVAMENTE un JSON con questo formato esatto, senza altro testo:\n"
                "{\n"
                '    "cert_id": "string",\n'
                '    "manufacturer": "string",\n'
                '    "standard": "MEG4",\n'
                '    "main_material": "string",\n'
                '    "main_diameter_mm": 0.0,\n'
                '    "main_mbl_tons": 0.0,\n'
                '    "main_length_m": 0.0,\n'
                '    "has_tail": false,\n'
                '    "tail_material": "",\n'
                '    "tail_diameter_mm": 0.0,\n'
                '    "tail_mbl_tons": 0.0,\n'
                '    "tail_length_m": 0.0\n'
                "}"
            )

            response = model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": img_bytes}
            ])

            result_dict = safe_extract_json(response.text)
            if result_dict:
                return result_dict

        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Immagine: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Parsing del testo estrapolato dal PDF."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model_name = resolve_working_model()
            model = genai.GenerativeModel(model_name)

            prompt = (
                "Estrai i dati di questo certificato cavi d'ormeggio MEG4 in JSON:\n"
                "{\n"
                '    "cert_id": "string",\n'
                '    "manufacturer": "string",\n'
                '    "standard": "MEG4",\n'
                '    "main_material": "string",\
