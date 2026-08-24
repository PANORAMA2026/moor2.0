"""
utils/pdf_parser.py
Parser di certificati PDF multi-produttore per estrazione automatica dati cavi (MBL, Diametro, Materiale).
"""

import re
from pypdf import PdfReader

def parse_line_certificate(pdf_file_stream) -> dict:
    """
    Estrae le informazioni chiave da un PDF di certificato cavo.
    """
    reader = PdfReader(pdf_file_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
        
    extracted_data = {
        "mbl_tons": None,
        "diameter_mm": None,
        "manufacturer": "Sconosciuto",
        "standard": "MEG4 Compliant"
    }
    
    # RegEx per MBL (es. "MBL: 120 t", "Breaking Load: 1200 kN")
    mbl_match = re.search(r'(?:MBL|Breaking Load|Carico di Rottura)[:\s]*([\d\.]+)\s*(kN|tons|t|MT)', text, re.IGNORECASE)
    if mbl_match:
        val, unit = float(mbl_match.group(1)), mbl_match.group(2).lower()
        if 'kn' in unit:
            extracted_data["mbl_tons"] = round(val * 0.10197, 1)
        else:
            extracted_data["mbl_tons"] = val

    # RegEx per Diametro (es. "Diameter: 64 mm", "Dia: 64mm")
    dia_match = re.search(r'(?:Diameter|Diametro|Dia)[:\s]*([\d\.]+)\s*mm', text, re.IGNORECASE)
    if dia_match:
        extracted_data["diameter_mm"] = float(dia_match.group(1))

    # RegEx semplice per identificare i principali produttori
    if "katradis" in text.lower():
        extracted_data["manufacturer"] = "Katradis"
    elif "lankhorst" in text.lower():
        extracted_data["manufacturer"] = "Lankhorst Ropes"
    elif "sampson" in text.lower():
        extracted_data["manufacturer"] = "Samson Rope"

    return extracted_data
