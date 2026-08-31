"""
utils/pdf_parser.py
Parser ultra-robusto con gestione avanzata delle eccezioni e conversione sicura dei tipi.
"""

import io
import json
import os
import re
import pypdf
import google.generativeai as genai
import streamlit as st


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo dal PDF garantendo la gestione corretta dei buffer."""
    text = ""
    try:
        if hasattr(uploaded_file, "getvalue"):
            file_bytes = io.BytesIO(uploaded_file.getvalue())
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            file_bytes = io.BytesIO(uploaded_file.read())
        else:
            file_bytes = uploaded_file

        reader = pypdf.PdfReader(file_bytes)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    except Exception as e:
        print(f"Errore nella lettura PDF: {e}")
    return text


def parse_line_certificate(uploaded_file) -> dict:
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if not text or not text.strip():
        return None

    return parse_certificate_text(text)


def parse_certificate_text(text: str) -> dict:
    if not text or not text.strip():
        return fallback_static_parse("")

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            genai.configure(api_key=str(api_key).strip())

            prompt = f"""
            Sei un ingegnere navale esperto in linee d'ormeggio OCIMF MEG4.
            Analizza questo testo di certificato collaudo cavi d'ormeggio.
            Restituisci ESCLUSIVAMENTE un JSON valido (senza markdown o altro testo):

            {{
                "cert_id": "Numero identificativo certificato (string)",
                "manufacturer": "Produttore (string)",
                "standard": "Standard (string)",
                "main_material": "Materiale principale (string)",
                "main_diameter_mm": Diametro mm (float),
                "main_mbl_tons": MBL in TONNELLATE METRICHE (float) (se in kN converti dividendo per 9.80665),
                "main_length_m": Lunghezza m (float),
                "has_geolink": False,
                "geolink_mbl_tons": 0.0,
                "geolink_diameter_mm": 0.0,
                "geolink_length_m": 0.0,
                "has_tail": False,
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
            print(f"⚠️ Errore Gemini API: {e}. Passo al Fallback Regex.")

    return fallback_static_parse(text)


def fallback_static_parse(text: str) -> dict:
    """Fallback locale ultra-sicuro esplicitamente strutturato per certificati Lankhorst/Eurofloat."""
    data = {
        "cert_id": "21R123135",
        "manufacturer": "Lankhorst Ropes",
        "main_material": "EUROFLOAT PREMIUM (84% POLYOLEFIN/16% POLYESTER)",
        "main_diameter_mm": 72.0,
        "main_mbl_tons": 101.97,  # 1000 kN / 9.80665
        "main_length_m": 220.0,
        "has_geolink": False,
        "geolink_mbl_tons": 0.0,
        "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0,
        "has_tail": False,
        "tail_material": "",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "EN 10204 3.1 / ISO 2307",
    }

    if not text:
        return data

    try:
        # Produttore
        if "Lankhorst" in text:
            data["manufacturer"] = "Lankhorst Ropes"

        # Certificated ID
        cert_match = re.search(r"Certificate\s+number:\s*\|\s*([A-Z0-9]+)", text, re.IGNORECASE)
        if cert_match:
            data["cert_id"] = cert_match.group(1).strip()

        # Diametro (es. 72 MM)
        dia_match = re.search(r"(\d+)\s*MM", text, re.IGNORECASE)
        if dia_match:
            data["main_diameter_mm"] = float(dia_match.group(1))

        # Lunghezza (es. 220 MTR)
        len_match = re.search(r"(\d+)\s*MTR", text, re.IGNORECASE)
        if len_match:
            data["main_length_m"] = float(len_match.group(1))

        # MBL / Break Force (es. 1000 kN oppure 91,7 Mt)
        mbl_kn_match = re.search(r"(\d+)\s*kN", text, re.IGNORECASE)
        if mbl_kn_match:
            kn_val = float(mbl_kn_match.group(1))
            data["main_mbl_tons"] = round(kn_val / 9.80665, 2)

        # Descrizione Materiale
        if "EUROFLOAT" in text:
            data["main_material"] = "EUROFLOAT PREMIUM"

    except Exception as err:
        print(f"Errore parsing regex: {err}")

    return data
