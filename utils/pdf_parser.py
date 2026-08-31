"""
utils/pdf_parser.py
Parser ultra-resistente con estrazione multilivello (PyMuPDF, pypdf, Gemini AI / OCR Fallback).
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
    """Estrae testo leggibile dal PDF provando più motori."""
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
    except Exception as e:
        st.write(f"⚠️ Errore lettura stream byte: {e}")
        return ""

    text = ""

    # Motore 1: PyMuPDF (fitz)
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
        except Exception as e:
            st.write(f"⚠️ PyMuPDF extraction warning: {e}")

    # Motore 2: pypdf
    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            if text.strip():
                return text.strip()
        except Exception as e:
            st.write(f"⚠️ pypdf extraction warning: {e}")

    return text.strip()


def parse_line_certificate(uploaded_file) -> dict:
    """Punto di ingresso per i file PDF salvati o trascinati."""
    if uploaded_file is None:
        return None

    # 1. Estrazione testo nativo
    text = extract_text_from_pdf(uploaded_file)
    
    # 2. Se abbiamo testo estratto, passiamo al parsing
    if text and text.strip():
        return parse_certificate_text(text)

    # 3. Se non c'è testo nativo (PDF scansionato/immagine), tenta Gemini Vision
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    
    if HAS_GEMINI and api_key and HAS_PYMUPDF:
        try:
            file_bytes = uploaded_file.getvalue() if hasattr(uploaded_file, "getvalue") else uploaded_file.read()
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-3.6-flash")

            prompt = """
            Sei un ingegnere navale. Analizza questo certificato di collaudo cavi d'ormeggio (MEG4).
            Estrai i dati reali e restituisci ESCLUSIVAMENTE un oggetto JSON con queste chiavi esatte:
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
                {"mime_type": "image/png", "data": img_bytes}
            ])

            clean_json = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_json)

        except Exception as err_vision:
            st.warning(f"⚠️ Chiamata Vision fallita: {err_vision}")

    # 4. Fallback estremo se né testo né AI Vision hanno prodotto risultati
    st.error("❌ Il PDF caricato non contiene layer di testo vettoriale e la chiave GEMINI_API_KEY non è configurata o attiva.")
    return None


def parse_certificate_text(text: str) -> dict:
    """Parse del testo estratto tramite Gemini o Regex."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            prompt = f"""
            Sei un ingegnere navale. Estrai i dati dal seguente certificato in formato JSON:
            {{
                "cert_id": "Numero certificato",
                "manufacturer": "Produttore",
                "standard": "Standard",
                "main_material": "Materiale",
                "main_diameter_mm": float,
                "main_mbl_tons": float (converti kN in tonnellate dividendo per 9.80665 se necessario),
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
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Gemini Text API: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Parser Regex di riserva."""
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
