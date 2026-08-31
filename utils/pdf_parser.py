"""
utils/pdf_parser.py
Parser dinamico per certificati d'ormeggio MEG4.
Estrae esclusivamente i dati reali dal PDF o testo inserito. Nessun dato hardcodato.
"""

import io
import json
import os
import re
import streamlit as st
import google.generativeai as genai

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
    """Estrae il testo reale dal buffer del PDF caricato."""
    if uploaded_file is None:
        return ""

    text = ""
    try:
        if hasattr(uploaded_file, "getvalue"):
            file_bytes = io.BytesIO(uploaded_file.getvalue())
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            file_bytes = io.BytesIO(uploaded_file.read())
        else:
            file_bytes = uploaded_file
    except Exception as e:
        print(f"Errore lettura buffer PDF: {e}")
        return ""

    # Motore 1: pdfplumber
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
            print(f"pdfplumber error: {e}")

    # Motore 2: pypdf (Fallback)
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
            print(f"pypdf error: {e}")

    return text.strip()


def parse_line_certificate(uploaded_file) -> dict:
    """Punto d'ingresso per file caricati via Drag & Drop."""
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if not text:
        return None

    return parse_certificate_text(text)


def parse_certificate_text(text: str) -> dict:
    """Parsing dinamico via Gemini AI o estrazione Regex se l'API non è disponibile."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            genai.configure(api_key=str(api_key).strip())

            prompt = f"""
            Sei un ingegnere navale esperto di linee d'ormeggio OCIMF MEG4.
            Analizza il seguente testo estratto DA UN CERTIFICATO REALE.
            
            Estrai i dati REALI presenti nel testo ed esegui la conversione di unità ove necessario.
            Restituisci ESCLUSIVAMENTE un JSON valido senza formattazione Markdown extra:

            {{
                "cert_id": "Numero identificativo certificato/collaudo",
                "manufacturer": "Nome produttore (es. Lankhorst, Gleistein, Samson, Katradis)",
                "standard": "Standard di prova o certificazione (es. ISO 2307, EN 10204 3.1, DNV)",
                "main_material": "Materiale o nome commerciale della main line",
                "main_diameter_mm": float (diametro nominale main line in mm),
                "main_mbl_tons": float (MBL o LDBF del cavo principale in TONNELLATE METRICHE. Se in kN dividi per 9.80665),
                "main_length_m": float (lunghezza main line in metri),
                "has_geolink": boolean (True solo se espressamente presente un lashing/geolink),
                "geolink_mbl_tons": float (MBL geolink in t, 0.0 se assente),
                "geolink_diameter_mm": float (diametro geolink in mm, 0.0 se assente),
                "geolink_length_m": float (0.0 se assente),
                "has_tail": boolean (True solo se espressamente presente una coda/tail nel certificato),
                "tail_material": string (materiale coda o vuoto),
                "tail_diameter_mm": float (diametro coda in mm, 0.0 se assente),
                "tail_mbl_tons": float (MBL coda in t, 0.0 se assente),
                "tail_length_m": float (lunghezza coda in m, 0.0 se assente)
            }}

            Testo del Certificato:
            {text}
            """

            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"response_mime_type": "application/json"}
            )
            parsed_json = json.loads(response.text)
            return parsed_json

        except Exception as e:
            print(f"⚠️ Errore API Gemini: {e}. Esecuzione Regex dinamico di backup.")

    # Se non c'è API key o l'API fallisce, usa l'estrazione Regex dinamica sul testo reale
    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Estrae dinamicamente i valori dal testo fornito tramite Regular Expressions."""
    data = {
        "cert_id": "N/A",
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
        "standard": "MEG4 / ISO 2307",
    }

    # ID Certificato
    cert_m = re.search(r"(?:Certificate\s*(?:number|no\.?|nr\.?)|Cert\.\s*n°)\s*:?\s*\|?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
    if cert_m:
        data["cert_id"] = cert_m.group(1).strip()

    # Produttore
    for mfr in ["Lankhorst", "Gleistein", "Samson", "Katradis", "Bridon", "Bexco", "Timm"]:
        if re.search(r"\b" + mfr + r"\b", text, re.IGNORECASE):
            data["manufacturer"] = mfr
            break

    # Diametro mm
    dia_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|MM)\b", text)
    if dia_m:
        data["main_diameter_mm"] = float(dia_m.group(1))

    # Lunghezza m
    len_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mtr|m|metres|metri)\b", text, re.IGNORECASE)
    if len_m:
        data["main_length_m"] = float(len_m.group(1))

    # MBL / Break Force (kN o Mt / t)
    mbl_kn = re.search(r"(\d+(?:\.\d+)?)\s*kN\b", text, re.IGNORECASE)
    mbl_mt = re.search(r"(\d+(?:[\.\,]\d+)?)\s*(?:Mt|t|tons|tonnes)\b", text, re.IGNORECASE)

    if mbl_kn:
        data["main_mbl_tons"] = round(float(mbl_kn.group(1)) / 9.80665, 2)
    elif mbl_mt:
        val_str = mbl_mt.group(1).replace(",", ".")
        data["main_mbl_tons"] = float(val_str)

    # Materiale
    mat_m = re.search(r"(?:Material|Composition|Description)\s*:?\s*([^\n\r]+)", text, re.IGNORECASE)
    if mat_m:
        data["main_material"] = mat_m.group(1).strip()

    # Restituisce None se non è riuscito a trovare neanche l'MBL o il diametro dal testo
    if data["main_mbl_tons"] == 0.0 and data["main_diameter_mm"] == 0.0 and data["cert_id"] == "N/A":
        return None

    return data
