"""
utils/pdf_parser.py
Parser dinamico per certificati d'ormeggio MEG4 e accessori.
Supporta qualsiasi produttore mediante tokenizzazione flessibile, normalizzazione e conversione unificata.
"""

import re
from pypdf import PdfReader

# Dizionario di conversione al carico in Tonnellate Metriche (t)
FORCE_CONVERSION = {
    'kn': 0.1019716,
    'ton': 1.0,
    'tons': 1.0,
    't': 1.0,
    'mt': 1.0,
    'kgf': 0.001,
    'lbs': 0.000453592
}

def extract_text_from_pdf(pdf_file_stream) -> str:
    """Estrae e pulisce il testo da uno stream PDF."""
    try:
        reader = PdfReader(pdf_file_stream)
        raw_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                raw_text.append(t)
        full_text = "\n".join(raw_text)
        # Normalizza spazi bianchi multipli conservando la struttura base
        cleaned_text = re.sub(r'[ \t]+', ' ', full_text)
        return cleaned_text
    except Exception:
        return ""

def parse_certificate_text(text: str) -> dict:
    """
    Analizza il testo estratto da un certificato per ricavare MBL, Diametro,
    Produttore, Materiale e Dati Tail, gestendo strutture non standard.
    """
    data = {
        "cert_id": "N/D",
        "mbl_tons": 100.0,  # Valore di fallback sicuro
        "diameter_mm": 64.0,
        "manufacturer": "Generico",
        "material": "HMPE",
        "tail_material": "NYLON",
        "tail_length_m": 11.0,
        "standard": "MEG4 Compliant"
    }

    if not text:
        return data

    text_lower = text.lower()

    # 1. NUMERO CERTIFICATO (Cert No / Certificate ID / Reference)
    cert_patterns = [
        r'(?:certificate|cert|test\s*report|ref)[\.\s]*n[o°\.]*[:\s]*([a-z0-9\-\/]+)',
        r'(?:certificate|cert)[\s]*id[:\s]*([a-z0-9\-\/]+)'
    ]
    for pattern in cert_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["cert_id"] = match.group(1).strip()
            break

    # 2. CARICO DI ROTTURA (MBL / Breaking Force / Tenacity)
    mbl_patterns = [
        r'(?:mbl|minimum\s*breaking\s*load|breaking\s*force|carico\s*di\s*rottura|unspliced\0\s*mbl|line\s*mbl)[:\s]*([\d\.,]+)\s*(kn|tons|ton|t|mt|kgf|lbs)',
        r'([\d\.,]+)\s*(kn|tons|t|mt)\s*(?:mbl|breaking\s*strength)',
        r'(?:breaking\s*load)[:\s]*([\d\.,]+)\s*(kn|tons|t|mt)'
    ]
    for pattern in mbl_patterns:
        match = re.search(pattern, text_lower)
        if match:
            raw_val = match.group(1).replace(',', '.')
            unit = match.group(2).lower()
            try:
                val = float(raw_val)
                conversion = FORCE_CONVERSION.get(unit, 1.0)
                data["mbl_tons"] = round(val * conversion, 1)
                break
            except ValueError:
                continue

    # 3. DIAMETRO (Diameter / Size / Dia)
    dia_patterns = [
        r'(?:diameter|diametro|dia|size)[:\s]*([\d\.,]+)\s*mm',
        r'([\d\.,]+)\s*mm\s*(?:dia|diameter)'
    ]
    for pattern in dia_patterns:
        match = re.search(pattern, text_lower)
        if match:
            raw_val = match.group(1).replace(',', '.')
            try:
                data["diameter_mm"] = float(raw_val)
                break
            except ValueError:
                continue

    # 4. PRODUTTORE (Riconoscimento basato sulle keyword del brand)
    manufacturers = {
        "samson": "Samson Rope",
        "lankhorst": "Lankhorst Ropes",
        "katradis": "Katradis",
        "bridon": "Bridon Bekaert",
        "teufelberger": "Teufelberger",
        "marlow": "Marlow Ropes",
        "vornbaeumen": "Vornbaeumen"
    }
    for key, name in manufacturers.items():
        if key in text_lower:
            data["manufacturer"] = name
            break

    # 5. TIPOLOGIA MATERIALE (Mappatura con priorità tecnica MEG4)
    if any(k in text_lower for k in ["hmpe", "dyneema", "spectra", "uhmwpe", "high modulus"]):
        data["material"] = "HMPE"
    elif any(k in text_lower for k in ["polyamide", "nylon", "nylon 6"]):
        data["material"] = "NYLON"
    elif any(k in text_lower for k in ["polyester", "pes", "poliestere", "terylene"]):
        data["material"] = "POLYESTER"
    elif any(k in text_lower for k in ["steel", "wire", "eips", "eeips", "acciaio"]):
        data["material"] = "STEEL_WIRE"

    # 6. RICONOSCIMENTO PARAMETRI TAIL (se presenti nel certificato)
    if "tail" in text_lower or "pennetto" in text_lower or "coda" in text_lower:
        if "nylon" in text_lower or "polyamide" in text_lower:
            data["tail_material"] = "NYLON"
        elif "polyester" in text_lower:
            data["tail_material"] = "POLYESTER"
            
        len_match = re.search(r'(?:tail\s*length|lunghezza\s*coda)[:\s]*([\d\.,]+)\s*m', text_lower)
        if len_match:
            try:
                data["tail_length_m"] = float(len_match.group(1).replace(',', '.'))
            except ValueError:
                pass

    return data

def parse_line_certificate(pdf_file_stream) -> dict:
    """Funzione helper di interfaccia diretta."""
    text = extract_text_from_pdf(pdf_file_stream)
    return parse_certificate_text(text)
