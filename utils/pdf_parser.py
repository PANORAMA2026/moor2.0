"""
utils/pdf_parser.py
Parser intelligente basato su Gemini API per certificati cavi d'ormeggio MEG4.
"""

import io
import json
import os
import re
import pypdf
import google.generativeai as genai
import streamlit as st


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo dal PDF leggendo il buffer di memoria in modo sicuro."""
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
        print(f"Errore nella lettura del file PDF: {e}")
    return text


def parse_line_certificate(uploaded_file) -> dict:
    """Funzione principale richiamata dal pulsante di parsing."""
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if not text or not text.strip():
        return None

    return parse_certificate_text(text)


def parse_certificate_text(text: str) -> dict:
    """Funzione di supporto/compatibilità richiamata dalle viste dell'app."""
    if not text or not text.strip():
        return fallback_static_parse("")

    # Recupera la chiave dai Secrets di Streamlit o dalle variabili d'ambiente
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            # .strip() rimuove eventuali spazi o ritorni a capo accidentali
            genai.configure(api_key=str(api_key).strip())

            prompt = f"""
            Sei un ingegnere navale esperto nella gestione di linee d'ormeggio navali secondo le linee guida OCIMF MEG4.
            Analizza il seguente testo estratto da un certificato di collaudo cavi d'ormeggio (mooring line certificate).
            
            Estrai ed elabora le seguenti informazioni restituendo ESCLUSIVAMENTE un oggetto JSON valido:

            {{
                "cert_id": "Numero identificativo del certificato/collaudo (string)",
                "manufacturer": "Nome del produttore (es. Lankhorst, Gleistein, Samson) (string)",
                "standard": "Standard di prova o certificazione (es. DIN EN ISO 2307 / DNV) (string)",
                "main_material": "Materiale o nome commerciale del cavo principale (string)",
                "main_diameter_mm": Diametro nominale della main line in mm (float),
                "main_mbl_tons": Break Force / MBL del cavo principale in TONNELLATE METRICHE (float). Se espressa in kN, converti dividendo per 9.80665,
                "main_length_m": Lunghezza totale della main line in metri (float),
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

            Testo del Certificato:
            {text}
            """

            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )

            return json.loads(response.text)

        except Exception as e:
            print(f"⚠️ Chiamata API Gemini non riuscita: {e}")

    return fallback_static_parse(text)


def fallback_static_parse(text: str) -> dict:
    """Fallback deterministico tramite Regex se l'API Gemini fallisce o non è presente."""
    data = {
        "cert_id": "N/A",
        "manufacturer": "Sconosciuto",
        "main_material": "Sintetico",
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
        "standard": "EN 10204 3.1 / MEG4",
    }

    if not text:
        return data

    # Produttore
    if "Lankhorst" in text:
        data["manufacturer"] = "Lankhorst Ropes"
    elif "Gleistein" in text:
        data["manufacturer"] = "Gleistein"
    elif "Samson" in text:
        data["manufacturer"] = "Samson"

    # ID Certificato
    cert_m = re.search(r"Certificate\s+number:?\s*\|\s*([A-Z0-9]+)", text, re.IGNORECASE) or re.search(r"Certificate\s+number:?\s*([A-Z0-9]+)", text, re.IGNORECASE)
    if cert_m:
        data["cert_id"] = cert_m.group(1).strip()

    # Diametro mm
    dia_m = re.search(r"(\d+)\s*MM", text, re.IGNORECASE)
    if dia_m:
        data["main_diameter_mm"] = float(dia_m.group(1))

    # Lunghezza m
    len_m = re.search(r"(\d+)\s*MTR", text, re.IGNORECASE)
    if len_m:
        data["main_length_m"] = float(len_m.group(1))

    # MBL (con conversione da kN a tonnellate se necessario)
    mbl_mt = re.search(r"([\d\,]+)\s*Mt", text, re.IGNORECASE)
    mbl_kn = re.search(r"(\d+)\s*kN", text, re.IGNORECASE)

    if mbl_mt:
        data["main_mbl_tons"] = float(mbl_mt.group(1).replace(",", "."))
    elif mbl_kn:
        data["main_mbl_tons"] = round(float(mbl_kn.group(1)) / 9.80665, 2)

    # Materiale
    mat_m = re.search(r"Material\s*\|\s*([^\n]+)", text, re.IGNORECASE)
    if mat_m:
        data["main_material"] = mat_m.group(1).strip()

    return data
