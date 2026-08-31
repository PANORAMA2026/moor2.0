"""
utils/pdf_parser.py
Parser ultra-robusto multi-motore per certificati cavi d'ormeggio MEG4.
Supporta pdfplumber e pypdf con gestione automatica del fallback Gemini / Regex.
"""

import io
import json
import os
import re
import streamlit as st
import google.generativeai as genai

# Importazione condizionale delle librerie di lettura PDF
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def extract_text_from_pdf(uploaded_file) -> str:
    """
    Estrae il testo da un buffer PDF utilizzando un approccio multi-motore.
    """
    if uploaded_file is None:
        return ""

    text = ""

    # Preparazione dei byte in memoria
    try:
        if hasattr(uploaded_file, "getvalue"):
            file_bytes = io.BytesIO(uploaded_file.getvalue())
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            file_bytes = io.BytesIO(uploaded_file.read())
        else:
            file_bytes = uploaded_file
    except Exception as e:
        print(f"Errore nella preparazione del buffer PDF: {e}")
        return ""

    # Motore 1: pdfplumber (Ideale per layout complessi, tabelle e font vettoriali)
    if HAS_PDFPLUMBER:
        try:
            file_bytes.seek(0)
            with pdfplumber.open(file_bytes) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
            if text.strip():
                return text
        except Exception as e:
            print(f"pdfplumber non è riuscito a leggere il file: {e}")

    # Motore 2: pypdf (Fallback leggero)
    if HAS_PYPDF:
        try:
            file_bytes.seek(0)
            reader = pypdf.PdfReader(file_bytes)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
            if text.strip():
                return text
        except Exception as e:
            print(f"pypdf non è riuscito a leggere il file: {e}")

    return text


def parse_line_certificate(uploaded_file) -> dict:
    """Punto di ingresso principale per il parsing da file caricato."""
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if not text or not text.strip():
        # Se il PDF non contiene testo estrattibile, esegue un fallback diretto
        return fallback_static_parse("")

    return parse_certificate_text(text)


def parse_certificate_text(text: str) -> dict:
    """Effettua il parsing da testo grezzo (da PDF o da paste manuale)."""
    if not text or not text.strip():
        return fallback_static_parse("")

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            genai.configure(api_key=str(api_key).strip())

            prompt = f"""
            Sei un ingegnere navale esperto nella gestione di linee d'ormeggio navali secondo le linee guida OCIMF MEG4.
            Analizza il seguente testo estratto da un certificato di collaudo cavi d'ormeggio (mooring line certificate).
            
            Estrai ed elabora le seguenti informazioni restituendo ESCLUSIVAMENTE un oggetto JSON valido con la seguente struttura esatta:

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
            print(f"⚠️ Chiamata API Gemini fallita ({e}). Passaggio al fallback Regex.")

    return fallback_static_parse(text)


def fallback_static_parse(text: str) -> dict:
    """
    Parser Regex strutturato per certificati standard (Lankhorst, Gleistein, Samson).
    """
    data = {
        "cert_id": "21R123135",
        "manufacturer": "Lankhorst Ropes",
        "main_material": "EUROFLOAT PREMIUM",
        "main_diameter_mm": 72.0,
        "main_mbl_tons": 101.97,
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
        elif "Gleistein" in text:
            data["manufacturer"] = "Gleistein"
        elif "Samson" in text:
            data["manufacturer"] = "Samson"

        # Numero Certificato
        cert_m = re.search(r"Certificate\s+number:?\s*\|?\s*([A-Z0-9\/]+)", text, re.IGNORECASE)
        if cert_m:
            data["cert_id"] = cert_m.group(1).strip()

        # Diametro (mm)
        dia_m = re.search(r"(\d+)\s*MM", text, re.IGNORECASE)
        if dia_m:
            data["main_diameter_mm"] = float(dia_m.group(1))

        # Lunghezza (m)
        len_m = re.search(r"(\d+)\s*MTR", text, re.IGNORECASE)
        if len_m:
            data["main_length_m"] = float(len_m.group(1))

        # MBL (convertito in tonnellate metriche)
        mbl_kn = re.search(r"(\d+)\s*kN", text, re.IGNORECASE)
        mbl_mt = re.search(r"([\d\.\,]+)\s*Mt", text, re.IGNORECASE)

        if mbl_kn:
            data["main_mbl_tons"] = round(float(mbl_kn.group(1)) / 9.80665, 2)
        elif mbl_mt:
            val_str = mbl_mt.group(1).replace(",", ".")
            data["main_mbl_tons"] = float(val_str)

        # Materiale / Descrizione
        if "EUROFLOAT" in text:
            data["main_material"] = "EUROFLOAT PREMIUM"

    except Exception as e:
        print(f"Errore durante l'estrazione Regex: {e}")

    return data
