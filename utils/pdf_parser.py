"""
utils/pdf_parser.py
Parser ultra-resistente per certificati cavi d'ormeggio MEG4.
Utilizza PyMuPDF (fitz) per l'estrazione testo ad alta precisione e Gemini Vision/Text per l'analisi.
"""

import io
import json
import os
import re
import streamlit as st
import google.generativeai as genai

# Utilizzo di PyMuPDF (fitz) - La libreria più potente per parsing PDF
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

# Fallback su pypdf
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


def extract_text_from_pdf(uploaded_file) -> str:
    """
    Estrae il testo dal PDF garantendo la gestione dei buffer PyMuPDF/pypdf.
    """
    if uploaded_file is None:
        return ""

    text = ""
    try:
        if hasattr(uploaded_file, "getvalue"):
            file_bytes = uploaded_file.getvalue()
        elif hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            file_bytes = uploaded_file.read()
        else:
            file_bytes = uploaded_file
    except Exception as e:
        print(f"Errore lettura stream byte PDF: {e}")
        return ""

    # MOTORE 1: PyMuPDF (fitz) - Estrae testo anche con font compressi/strani
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
            print(f"Errore PyMuPDF: {e}")

    # MOTORE 2: pypdf (Fallback)
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
            print(f"Errore pypdf: {e}")

    return text.strip()


def parse_line_certificate(uploaded_file) -> dict:
    """Punto di ingresso principale per file PDF."""
    if uploaded_file is None:
        return None

    # 1. Tenta l'estrazione del testo
    text = extract_text_from_pdf(uploaded_file)
    
    # 2. Se c'è testo estratto, esegui il parsing normale
    if text and text.strip():
        return parse_certificate_text(text)

    # 3. SE IL TESTO È VUOTO (PDF visivo/scansione): Tenta l'analisi visiva diretta con Gemini Vision
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if api_key and HAS_PYMUPDF:
        try:
            if hasattr(uploaded_file, "getvalue"):
                file_bytes = uploaded_file.getvalue()
            else:
                uploaded_file.seek(0)
                file_bytes = uploaded_file.read()

            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            doc.close()

            genai.configure(api_key=str(api_key).strip())
            model = genai.GenerativeModel("gemini-2.5-flash")

            prompt = """
            Sei un ingegnere navale. Questa immagine è un certificato di collaudo per cavi d'ormeggio navali.
            Estrai i dati visibili ed esegui le conversioni necessarie.
            Restituisci ESCLUSIVAMENTE un JSON valido (senza markdown):

            {
                "cert_id": "Numero certificato (string)",
                "manufacturer": "Produttore (string)",
                "standard": "Standard (string)",
                "main_material": "Materiale principale (string)",
                "main_diameter_mm": float (diametro mm),
                "main_mbl_tons": float (MBL in tonnellate metriche. Se in kN dividi per 9.80665),
                "main_length_m": float (lunghezza metri),
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

        except Exception as e:
            print(f"Errore Gemini Vision: {e}")

    return None


def parse_certificate_text(text: str) -> dict:
    """Parsing da testo estratto via Gemini AI o Regex dinamico."""
    if not text or not text.strip():
        return None

    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            genai.configure(api_key=str(api_key).strip())

            prompt = f"""
            Sei un ingegnere navale esperto di linee d'ormeggio OCIMF MEG4.
            Analizza il seguente testo estratto da un certificato di collaudo cavi.
            Estrai i dati REALI e restituisci ESCLUSIVAMENTE un JSON valido:

            {{
                "cert_id": "Numero certificato",
                "manufacturer": "Nome produttore",
                "standard": "Standard certificazione",
                "main_material": "Materiale o tipo cavo",
                "main_diameter_mm": float (diametro mm),
                "main_mbl_tons": float (MBL in TONNELLATE METRICHE. Se in kN dividi per 9.80665),
                "main_length_m": float (lunghezza metri),
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
            print(f"⚠️ Errore Gemini API: {e}")

    return dynamic_regex_parse(text)


def dynamic_regex_parse(text: str) -> dict:
    """Fallback Regex dinamico."""
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

    cert_m = re.search(r"(?:Certificate\s*(?:number|no\.?|nr\.?)|Cert\.\s*n°)\s*:?\s*\|?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
    if cert_m:
        data["cert_id"] = cert_m.group(1).strip()

    for mfr in ["Lankhorst", "Gleistein", "Samson", "Katradis", "Bridon", "Bexco", "Timm"]:
        if re.search(r"\b" + mfr + r"\b", text, re.IGNORECASE):
            data["manufacturer"] = mfr
            break

    dia_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm|MM)\b", text)
    if dia_m:
        data["main_diameter_mm"] = float(dia_m.group(1))

    len_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:mtr|m|metres|metri)\b", text, re.IGNORECASE)
    if len_m:
        data["main_length_m"] = float(len_m.group(1))

    mbl_kn = re.search(r"(\d+(?:\.\d+)?)\s*kN\b", text, re.IGNORECASE)
    mbl_mt = re.search(r"(\d+(?:[\.\,]\d+)?)\s*(?:Mt|t|tons|tonnes)\b", text, re.IGNORECASE)

    if mbl_kn:
        data["main_mbl_tons"] = round(float(mbl_kn.group(1)) / 9.80665, 2)
    elif mbl_mt:
        val_str = mbl_mt.group(1).replace(",", ".")
        data["main_mbl_tons"] = float(val_str)

    if data["main_mbl_tons"] == 0.0 and data["main_diameter_mm"] == 0.0 and data["cert_id"] == "N/A":
        return None

    return data
