"""
utils/pdf_parser.py
Parser ultra-veloce con selezione dinamica del modello ed estrazione istantanea del testo.
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
    """Estrae i byte in modo sicuro azzerando lo stream pointer."""
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
    """Estrae il testo vettoriale dal PDF via PyMuPDF in pochissimi millisecondi."""
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


def get_working_model_name():
    """Rileva automaticamente il primo modello valido e attivo associato alla tua API Key."""
    try:
        models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
        if models:
            # Pulisce eventuale prefisso 'models/'
            selected = models[0].replace("models/", "")
            return selected
    except Exception:
        pass
    return "gemini-1.5-flash"


def parse_line_certificate(uploaded_file) -> dict:
    """Parsing ultra-veloce con fallback dinamico."""
    if uploaded_file is None:
        return None

    # 1. Tentativo di estrazione testo nativo istantanea
    text = extract_text_from_pdf(uploaded_file)
    if text and len(text) > 30:
        return parse_certificate_text(text)

    # 2. Fallback per PDF Scansionati
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
            model_name = get_working_model_name()
            model = genai.GenerativeModel(model_name)

            prompt = 'Estrai dati certificato MEG4 in JSON: {"cert_id":"","manufacturer":"","main_material":"","main_diameter_mm":0.0,"main_mbl_tons":0.0,"main_length_m":0.0,"standard":"MEG4"}'

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
    """Invia il testo estratto per una risposta immediata (sotto il secondo)."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model_name = get_working_model_name()
            model = genai.GenerativeModel(model_name)

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

Testo certificato:
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
