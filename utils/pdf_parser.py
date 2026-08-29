"""
utils/pdf_parser.py
Parser adattativo per certificati d'ormeggio MEG4 e accessori multi-componente.
Supporta qualsiasi produttore mediante tokenizzazione flessibile, normalizzazione Eur/USA
ed estrazione multi-modulo (Main Line, GeoLink e Tail).
"""

import re
from pypdf import PdfReader

# Conversione a Tonnellate Metriche (t)
FORCE_CONVERSION = {
    'kn': 0.1019716,
    'ton': 1.0,
    'tons': 1.0,
    't': 1.0,
    'mt': 1.0,
    'kgf': 0.001,
    'lbs': 0.000453592
}

def clean_numeric(val_str: str) -> float:
    """Normalizza numeri in formato Europeo (1.220,78) o USA (1,220.78) in float standard."""
    if not val_str:
        return 0.0
    val_str = val_str.strip()
    if "." in val_str and "," in val_str:
        if val_str.rfind(",") > val_str.rfind("."):
            val_str = val_str.replace(".", "").replace(",", ".")
        else:
            val_str = val_str.replace(",", "")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")
    
    try:
        cleaned = re.sub(r"[^\d\.]", "", val_str)
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0

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
        return re.sub(r'[ \t]+', ' ', full_text)
    except Exception:
        return ""

def parse_certificate_text(text: str) -> dict:
    """
    Analizza il testo estratto per ricavare Main Line, GeoLink e Tail
    indipendentemente dal layout del produttore.
    """
    data = {
        "cert_id": "CERT-GENERIC",
        "manufacturer": "Generico",
        "standard": "MEG4 / ISO 2307",
        # Main Line
        "main_material": "HMPE",
        "main_diameter_mm": 64.0,
        "main_mbl_tons": 100.0,
        "main_length_m": 220.0,
        # GeoLink / Connector
        "has_geolink": False,
        "geolink_id": "N/A",
        "geolink_mbl_tons": 0.0,
        "geolink_length_m": 0.0,
        # Tail / Gazza
        "has_tail": False,
        "tail_material": "NYLON",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 11.0,
        "raw_text": text
    }

    if not text:
        return data

    text_lower = text.lower()

    # 1. PRODUTTORE
    manufacturers = {
        "gleistein": "Gleistein Ropes",
        "lankhorst": "Lankhorst Ropes",
        "bexco": "Bexco",
        "samson": "Samson Rope",
        "katradis": "Katradis",
        "bridon": "Bridon Bekaert",
        "teufelberger": "Teufelberger",
        "marlow": "Marlow Ropes"
    }
    for key, name in manufacturers.items():
        if key in text_lower:
            data["manufacturer"] = name
            break

    # 2. NUMERO CERTIFICATO
    cert_patterns = [
        r'(?:certificate\s*(?:no\.|number)?|certificatenumber)[\s:]*([a-z0-9\-\/_]+)',
        r'(?:certificate|cert|test\s*report|ref)[\.\s]*n[o°\.]*[:\s]*([a-z0-9\-\/_]+)',
        r'wz\d+-\d+' # Pattern specifico Gleistein (es. WZ25-7201)
    ]
    for pattern in cert_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data["cert_id"] = match.group(1 if match.groups() else 0).strip()
            break

    # 3. MAIN LINE - DIAMETRO & MBL
    dia_match = re.search(r'(?:diameter|diametro|dia|size|nominal diameter)[\s:]*(\d+[\.,]?\d*)\s*mm', text_lower)
    if not dia_match:
        dia_match = re.search(r'(\d+)\s*mm\s*Ø', text, re.IGNORECASE)
    if dia_match:
        data["main_diameter_mm"] = clean_numeric(dia_match.group(1))

    mbl_match = re.search(r'(?:mbl|minimum\s*breaking\s*load|breaking\s*load|break\0\s*load\s*spliced|break\s*load\s*linear|ldbf)[:\s]*([\d\.,]+)\s*(kn|tons|ton|t|mt|kgf|lbs)', text_lower)
    if mbl_match:
        raw_val = clean_numeric(mbl_match.group(1))
        unit = mbl_match.group(2).lower()
        conv = FORCE_CONVERSION.get(unit, 1.0)
        data["main_mbl_tons"] = round(raw_val * conv, 1)

    # Main Line Material
    if any(k in text_lower for k in ["dyneema", "hmpe", "flextwin", "lanko force", "uhmwpe"]):
        data["main_material"] = "HMPE (Dyneema SK78)"
    elif any(k in text_lower for k in ["eurofloat", "polyolefin", "bexcoline"]):
        data["main_material"] = "Polyolefin / Polyester Blend"
    elif "polyester" in text_lower or "pes" in text_lower:
        data["main_material"] = "Polyester"

    # Main Line Length
    len_match = re.search(r'(\d+[\.,]?\d*)\s*(?:m|meter|mtr)\b', text_lower)
    if len_match:
        val = clean_numeric(len_match.group(1))
        if 10.0 <= val <= 500.0:
            data["main_length_m"] = val

    # 4. RILEVAMENTO GEOLINK / CONNECTOR
    if "geolink" in text_lower or "lashing" in text_lower or "connector" in text_lower:
        data["has_geolink"] = True
        data["geolink_id"] = f"GL-{data['cert_id']}"
        data["geolink_mbl_tons"] = round(data["main_mbl_tons"] * 1.05, 1)
        data["geolink_length_m"] = 5.0

    # 5. RILEVAMENTO TAIL / GAZZA / STROP
    if "tail" in text_lower or "strop" in text_lower or "geosquare" in text_lower or "gazza" in text_lower:
        data["has_tail"] = True
        data["tail_diameter_mm"] = round(data["main_diameter_mm"] * 1.25, 0)
        
        # MBL specifico Tail se presente
        tail_mbl_match = re.search(r'(?:break\s*load\s*grommet|tail\s*mbl|tdbf)[:\s]*([\d\.,]+)\s*(kn|tons|t|mt)', text_lower)
        if tail_mbl_match:
            raw_v = clean_numeric(tail_mbl_match.group(1))
            u = tail_mbl_match.group(2).lower()
            data["tail_mbl_tons"] = round(raw_v * FORCE_CONVERSION.get(u, 1.0), 1)
        else:
            data["tail_mbl_tons"] = round(data["main_mbl_tons"] * 1.10, 1)

        if "nylon" in text_lower or "polyamide" in text_lower:
            data["tail_material"] = "NYLON"
        elif "polyester" in text_lower or "pes" in text_lower:
            data["tail_material"] = "POLYESTER"

    return data

def parse_line_certificate(pdf_file_stream) -> dict:
    """Funzione helper di interfaccia diretta."""
    text = extract_text_from_pdf(pdf_file_stream)
    return parse_certificate_text(text)
