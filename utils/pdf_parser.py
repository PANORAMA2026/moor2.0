"""
utils/pdf_parser.py
Parser di certificati PDF multi-produttore per estrazione automatica dati cavi (MBL, Diametro, Materiale).
"""

import re
from pypdf import PdfReader


def extract_text_from_pdf(pdf_file_stream) -> str:
  """Estrae tutto il testo da un file stream PDF caricato tramite Streamlit."""
  try:
    reader = PdfReader(pdf_file_stream)
    text = ""
    for page in reader.pages:
      extracted = page.extract_text()
      if extracted:
        text += extracted + "\n"
    return text
  except Exception:
    return ""


def parse_certificate_text(text: str) -> dict:
  """Analizza il testo estratto da un certificato per ricavare MBL, Diametro, Produttore e Materiale."""
  extracted_data = {
      "cert_id": None,
      "mbl_tons": None,
      "diameter_mm": None,
      "manufacturer": "Sconosciuto",
      "material": "HMPE",
      "standard": "MEG4 Compliant",
  }

  # RegEx Cert ID
  cert_match = re.search(
      r"(?:Certificate No|Cert\.?\s*ID|Certificato N°)[:\s]*([A-Z0-9\-\/]+)",
      text,
      re.IGNORECASE,
  )
  if cert_match:
    extracted_data["cert_id"] = cert_match.group(1).strip()

  # RegEx MBL (es. "MBL: 120 t", "Breaking Load: 1200 kN")
  mbl_match = re.search(
      r"(?:MBL|Breaking Load|Carico di Rottura)[:\s]*([\d\.]+)\s*(kN|tons|t|MT)",
      text,
      re.IGNORECASE,
  )
  if mbl_match:
    val = float(mbl_match.group(1))
    unit = mbl_match.group(2).lower()
    if "kn" in unit:
      extracted_data["mbl_tons"] = round(val * 0.10197, 1)
    else:
      extracted_data["mbl_tons"] = val

  # RegEx Diametro (es. "Diameter: 64 mm", "Dia: 64mm")
  dia_match = re.search(
      r"(?:Diameter|Diametro|Dia)[:\s]*([\d\.]+)\s*mm", text, re.IGNORECASE
  )
  if dia_match:
    extracted_data["diameter_mm"] = float(dia_match.group(1))

  # Identificazione Produttore
  text_lower = text.lower()
  if "katradis" in text_lower:
    extracted_data["manufacturer"] = "Katradis"
  elif "lankhorst" in text_lower:
    extracted_data["manufacturer"] = "Lankhorst Ropes"
  elif "samson" in text_lower or "sampson" in text_lower:
    extracted_data["manufacturer"] = "Samson Rope"
  elif "bridon" in text_lower:
    extracted_data["manufacturer"] = "Bridon Bekaert"

  # Identificazione Materiale
  if "hmpe" in text_lower or "dyneema" in text_lower:
    extracted_data["material"] = "HMPE"
  elif "polyester" in text_lower or "poliestere" in text_lower:
    extracted_data["material"] = "Polyester"
  elif "nylon" in text_lower or "polyamide" in text_lower:
    extracted_data["material"] = "Nylon"

  return extracted_data


def parse_line_certificate(pdf_file_stream) -> dict:
  """Funzione helper legacy di fallback."""
  text = extract_text_from_pdf(pdf_file_stream)
  return parse_certificate_text(text)
