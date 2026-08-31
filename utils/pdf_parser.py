"""
utils/pdf_parser.py
Parser ultra-veloce e robusto con schema Pydantic per prevenire stringhe non terminate.
"""

import json
import os
import re
import streamlit as st
from pydantic import BaseModel, Field

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


# Schema di output garantito via Pydantic
class MooringCertificateData(BaseModel):
    cert_id: str = Field(default="UNKNOWN")
    manufacturer: str = Field(default="N/A")
    standard: str = Field(default="MEG4")
    main_material: str = Field(default="N/A")
    main_diameter_mm: float = Field(default=0.0)
    main_mbl_tons: float = Field(default=0.0)
    main_length_m: float = Field(default=0.0)
    has_tail: bool = Field(default=False)
    tail_material: str = Field(default="")
    tail_diameter_mm: float = Field(default=0.0)
    tail_mbl_tons: float = Field(default=0.0)
    tail_length_m: float = Field(default=0.0)


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
    """Estrae il testo vettoriale in pochi millisecondi via PyMuPDF."""
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
    """Funzione principale per il parsing del certificato."""
    if uploaded_file is None:
        return None

    # 1. Tentativo di estrazione da testo vettoriale
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
            # Risoluzione a 80 DPI per velocità massima ed elaborazione immediata
            pix = page.get_pixmap(dpi=80)
            img_bytes = pix.tobytes("jpeg")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel(MODEL_NAME)

            prompt = "Sei un ingegnere navale. Estrai i dati tecnici di questo certificato cavi d'ormeggio MEG4."

            response = model.generate_content(
                [prompt, {"mime_type": "image/jpeg", "data": img_bytes}],
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": MooringCertificateData,
                    "temperature": 0.0,
                }
            )

            return json.loads(response.text)

        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Immagine: {e}")

    return dynamic_regex_parse(text)


def parse_certificate_text(text: str) -> dict:
    """Parsing del testo vettoriale con schema rigoroso."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if HAS_GEMINI and api_key:
        try:
            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel(MODEL_NAME)

            prompt = f"Estrai i dati tecnici di questo certificato cavi d'ormeggio MEG4:\n\n{text[:2500]}"

            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "response_schema": MooringCertificateData,
                    "temperature": 0.0,
                }
            )

            return json.loads(response.text)
        except Exception as e:
            st.warning(f"⚠️ Errore Parsing Testo: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback offline basato su Regex."""
    data = {
        "cert_id": "UNKNOWN", "manufacturer": "N/A", "main_material": "N/A",
        "main_diameter_mm": 0.0, "main_mbl_tons": 0.0, "main_length_m": 0.0,
        "has_tail": False, "tail_material": "", "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0, "tail_length_m": 0.0, "standard": "MEG4"
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
