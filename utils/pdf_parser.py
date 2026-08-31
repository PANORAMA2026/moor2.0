"""
utils/pdf_parser.py
Parser ultra-veloce con invio diretto dei byte PDF a Gemini 3.6 Flash.
"""

import io
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
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo nativo dal PDF se presente."""
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
    except Exception:
        return ""

    text = ""

    if HAS_PYMUPDF:
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in doc:
                t = page.get_text("text")
                if t:
                    text += t + "\n"
            doc.close()
            if text.strip():
                return text.strip()
        except Exception:
            pass

    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            if text.strip():
                return text.strip()
        except Exception:
            pass

    return text.strip()


def parse_line_certificate(uploaded_file) -> dict:
    """Invio rapido diretto dei byte PDF a Gemini 3.6 Flash."""
    if uploaded_file is None:
        return None

    if hasattr(uploaded_file, "getvalue"):
        file_bytes = uploaded_file.getvalue()
    elif hasattr(uploaded_file, "read"):
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
    else:
        file_bytes = uploaded_file

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            
            # Utilizza esattamente il modello 3.6-flash operato dalla tua API key
            model = genai.GenerativeModel("gemini-3.6-flash")

            prompt = """
            Sei un ingegnere navale esperto di linee d'ormeggio MEG4.
            Analizza questo certificato PDF ed estrai i dati reali.
            Restituisci ESCLUSIVAMENTE un JSON valido con questa struttura:
            {
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
            }
            """

            response = model.generate_content([
                prompt,
                {"mime_type": "application/pdf", "data": file_bytes}
            ], generation_config={"response_mime_type": "application/json"})

            return json.loads(response.text)

        except Exception as err_fast:
            st.warning(f"⚠️ Chiamata Gemini 3.6 fallita: {err_fast}")

    # Fallback su estrazione testo locale se non c'è rete/chiave
    text = extract_text_from_pdf(uploaded_file)
    if text:
        return parse_certificate_text(text)

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Parse del testo grezzo incollato."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")
            
            prompt = f"""
            Estrai i dati dal seguente certificato in formato JSON:
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

            Testo:
            {text}
            """
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Gemini Text API: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback locale con regex."""
    data = {
        "cert_id": "UNKNOWN",
        "manufacturer": "N/A",
        "main_material": "N/A",
        "main_diameter_mm": 0.0,
        "main_mbl_tons": 0.0,
        "main_length_m": 0.0,
        "has_geolink": False,
        "geolink_mbl_tons": 0.0,
        "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0,
        "has_tail": False,
        "tail_material": "",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "MEG4",
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
