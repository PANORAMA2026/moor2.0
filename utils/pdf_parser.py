"""
utils/pdf_parser.py
Parser intelligente basato su AI per certificati di collaudo cavi d'ormeggio multi-componente.
Analizza Main Line, GeoLink e Tail per qualsiasi produttore (Gleistein, Samson, Lankhorst, ecc.)
restituendo una struttura dati compatibile con MEG4.
"""

import json
import os
import re
import pypdf
import google.generativeai as genai
import streamlit as st


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae l'intero contenuto testuale da tutte le pagine del file PDF."""
    text = ""
    try:
        # Reset del puntatore per garantire la lettura da inizio file
        uploaded_file.seek(0)
        reader = pypdf.PdfReader(uploaded_file)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
    except Exception as e:
        print(f"Errore nella lettura del file PDF: {e}")
    return text


def parse_line_certificate(uploaded_file) -> dict:
    """
    Funzione principale d'ingresso: estrae il testo dal PDF e invia
    la richiesta al parser AI.
    """
    if uploaded_file is None:
        return None

    text = extract_text_from_pdf(uploaded_file)
    if not text.strip():
        # Ritorna None se il PDF non contiene testo estraibile (es. scansione raster senza OCR)
        return None

    return parse_certificate_with_ai(text)


def parse_certificate_with_ai(text: str) -> dict:
    """
    Utilizza l'API di Gemini per analizzare la struttura semantica del certificato
    ed estrarre i dati in formato JSON standardizzato.
    """
    # Recupera l'API Key dalle impostazioni di Streamlit Secrets o dalle variabili d'ambiente
    api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("⚠️ GEMINI_API_KEY non trovata. Utilizzo del fallback statico.")
        return fallback_static_parse(text)

    try:
        genai.configure(api_key=api_key)

        prompt = f"""
        Sei un ingegnere navale esperto nella gestione di linee d'ormeggio navali secondo le linee guida OCIMF MEG4.
        Analizza il seguente testo estratto da un certificato di collaudo e collaudo cavi d'ormeggio (mooring line certificate).
        
        Estrai ed elabora le seguenti informazioni restituendo ESCLUSIVAMENTE un oggetto JSON valido con la seguente struttura esatta:

        {{
            "cert_id": "Numero identificativo del certificato/collaudo (string)",
            "manufacturer": "Nome del produttore (es. Gleistein, Samson, Lankhorst, Katradis) (string)",
            "standard": "Standard di prova o certificazione (es. DIN EN ISO 2307 / DNV / Lloyd's) (string)",
            "main_material": "Materiale o nome commerciale del cavo principale (es. Dyneema SK78, HMPE, Polyester) (string)",
            "main_diameter_mm": Diametro nominale della main line in mm (float),
            "main_mbl_tons": Break Force / MBL del cavo principale in TONNELLATE METRICHE (float). Se espressa in kN, converti dividendo per 9.80665,
            "main_length_m": Lunghezza totale della main line in metri (float),
            "has_geolink": True se nel certificato o nella linea è presente un componente GeoLink / Lashing, altrimenti False (boolean),
            "geolink_mbl_tons": MBL del GeoLink in Tonnellate metriche (float, 0.0 se non presente),
            "geolink_diameter_mm": Diametro o dimensione del GeoLink in mm (float, 0.0 se non presente),
            "geolink_length_m": Lunghezza del GeoLink in metri (float, 0.0 se non presente),
            "has_tail": True se nel certificato è presente una coda d'ormeggio (Mooring Tail / Grommet), altrimenti False (boolean),
            "tail_material": Materiale o tipo della coda d'ormeggio (es. PP/PE Bipo, Poliestere) (string, "" se assente),
            "tail_diameter_mm": Diametro della coda d'ormeggio in mm (float, 0.0 se assente),
            "tail_mbl_tons": MBL della coda d'ormeggio in TONNELLATE METRICHE (float, 0.0 se assente),
            "tail_length_m": Lunghezza della coda d'ormeggio in metri (float, 0.0 se assente)
        }}

        Testo del Certificato:
        {text}
        """

        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )

        # Parsing dell'output JSON restituito dall'AI
        data = json.loads(response.text)
        return data

    except Exception as e:
        print(f"⚠️ Errore durante l'elaborazione AI: {e}. Esecuzione del fallback.")
        return fallback_static_parse(text)


def fallback_static_parse(text: str) -> dict:
    """
    Fallback basato su regole locali ed estrazione regex
    in caso di assenza di API Key o problemi di rete.
    """
    data = {
        "cert_id": "N/A",
        "manufacturer": "Sconosciuto",
        "main_material": "Sintetico Generic",
        "main_diameter_mm": 50.0,
        "main_mbl_tons": 100.0,
        "main_length_m": 220.0,
        "has_geolink": "GeoLink" in text or "Lashing" in text,
        "geolink_mbl_tons": 0.0,
        "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0,
        "has_tail": "Tail" in text or "Grommet" in text,
        "tail_material": "",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "ISO 2307",
    }

    cert_match = re.search(r"Certificate\s+(?:no\.|number)?:?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
    if cert_match:
        data["cert_id"] = cert_match.group(1).strip()

    if "Gleistein" in text:
        data["manufacturer"] = "Gleistein"

    return data
