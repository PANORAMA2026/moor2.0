"""
utils/pdf_parser.py
Parser ultra-veloce con estrazione testo locale istantanea + Gemini 3.6 Flash.
"""

import json
import os
import re
import streamlit as st

try:
    import fitz  # PyMuPDF (Esecuzione ultra-veloce)
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def extract_fast_text(uploaded_file) -> str:
    """Estrae il testo vettoriale dal PDF in pochissimi millisecondi via PyMuPDF."""
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

    # 1. Estrazione testo locale (quasi istantanea)
    text = extract_fast_text(uploaded_file)

    # 2. Se abbiamo il testo, inviamo SOLO il testo a Gemini (risposta in 1 secondo)
    if text:
        return parse_certificate_text(text)

    # 3. Fallback per PDF Scansionati (Convertito in JPEG compresso)
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            # Pixmap leggera per non appesantire il payload
            pix = page.get_pixmap(dpi=100)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")

            prompt = """
            Estrai i dati dal certificato in JSON:
            {
                "cert_id": "string", "manufacturer": "string", "standard": "string",
                "main_material": "string", "main_diameter_mm": float, "main_mbl_tons": float,
                "main_length_m": float, "has_geolink": false, "geolink_mbl_tons": 0.0,
                "geolink_diameter_mm": 0.0, "geolink_length_m": 0.0, "has_tail": false,
                "tail_material": "", "tail_diameter_mm": 0.0, "tail_mbl_tons": 0.0, "tail_length_m": 0.0
            }
            """

            response = model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": img_bytes}
            ], generation_config={"response_mime_type": "application/json"})

            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Vision: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Invia solo il testo a Gemini 3.6 Flash per una risposta immediata."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")

            prompt = f"""
            Sei un ingegnere navale. Estrai i dati dal seguente testo di certificato cavi MEG4.
            Restituisci ESCLUSIVAMENTE un oggetto JSON valido con queste chiavi:
            {{
                "cert_id": "string",
                "manufacturer": "string",
                "standard": "string",
                "main_material": "string",
                "main_diameter_mm": float,
                "main_mbl_tons": float,
                "main_length_m": float,
                "has_geolink": false,
                "geolink_mbl_tons": 0.0,
                "geolink_diameter_mm": 0.0,
                "geolink_length_m": 0.0,
                "has_tail": false,
                "tail_material": "",
                "tail_diameter_mm": 0.0,
                "tail_mbl_tons": 0.0,
                "tail_length_m": 0.0
            }}

            Testo certificato:
            {text[:4000]}
            """

            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
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
