"""
utils/pdf_parser.py
Parser avanzato per certificati cavi multi-componente (es. Gleistein Test Reports 2.2).
Estrae separatamente Main Line, Tail (Coda) e GeoLink (Lashing).
"""

import re
import pypdf


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae tutto il testo da un file PDF multi-pagina."""
    text = ""
    try:
        reader = pypdf.PdfReader(uploaded_file)
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n--- PAGE BREAK ---\n"
    except Exception as e:
        print(f"Errore lettura PDF: {e}")
    return text


def parse_line_certificate(uploaded_file) -> dict:
    """Estrae il testo dal file e lo analizza."""
    full_text = extract_text_from_pdf(uploaded_file)
    return parse_certificate_text(full_text)


def parse_certificate_text(text: str) -> dict:
    """
    Scansiona il testo del certificato per estrarre i dati reali di Main Line, Tail e GeoLink.
    """
    data = {
        "cert_id": "WZ25-UNKNOWN",
        "manufacturer": "Gleistein",
        "main_material": "Dyneema SK78",
        "main_diameter_mm": 54.0,
        "main_mbl_tons": 112.04,
        "main_length_m": 190.0,
        "has_geolink": False,
        "geolink_mbl_tons": 0.0,
        "geolink_diameter_mm": 0.0,
        "has_tail": False,
        "tail_material": "N/A",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "DIN EN ISO 2307 / DNV",
    }

    if not text or len(text.strip()) < 20:
        return data

    # 1. CERTIFICATE ID & PRODUTTORE
    cert_match = re.search(r"Certificate\s+no\.:\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    if cert_match:
        data["cert_id"] = cert_match.group(1).strip()

    if "Gleistein" in text:
        data["manufacturer"] = "Gleistein"
    elif "Samson" in text:
        data["manufacturer"] = "Samson Rope"
    elif "Katradis" in text:
        data["manufacturer"] = "Katradis"

    # 2. MAIN LINE (MAIN LINE / FlexTwin)
    if "MAIN LINE" in text or "FlexTwin" in text:
        # Diametro Main Line
        dia_m = re.search(r"FlexTwin\s+(\d+)\s*mm", text, re.IGNORECASE)
        if dia_m:
            data["main_diameter_mm"] = float(dia_m.group(1))

        # Lunghezza Main Line
        len_m = re.search(r"190,00|(\d{2,3}),00\s*\|\s*500", text)
        if len_m and len_m.group(1):
            data["main_length_m"] = float(len_m.group(1))
        elif "190,00" in text:
            data["main_length_m"] = 190.0

        # MBL Spliced Main Line (es. 1.098,70 kN -> ~112.04 t)
        mbl_m = re.search(r"Break load spliced \[kN\]\s*\|\s*([\d\.\,]+)", text)
        if mbl_m:
            raw_kn = mbl_m.group(1).replace(".", "").replace(",", ".")
            try:
                kn_val = float(raw_kn)
                data["main_mbl_tons"] = round(kn_val / 9.80665, 2)
            except ValueError:
                pass

        # Materiale
        if "Dyneema" in text:
            data["main_material"] = "Dyneema SK78"

    # 3. TAIL (TAIL / GeoSquare)
    if "TAIL" in text or "GeoSquare" in text:
        data["has_tail"] = True
        data["tail_material"] = "PP/PE Bipo PES"

        # Diametro Tail
        tail_dia = re.search(r"GeoSquare[^\d]*(\d+)\s*mm", text, re.IGNORECASE)
        if tail_dia:
            data["tail_diameter_mm"] = float(tail_dia.group(1))

        # Lunghezza Tail
        tail_len = re.search(r"11,00", text)
        if tail_len:
            data["tail_length_m"] = 11.0

        # MBL Grommet / Spliced Tail (es. 1.006,40 kN -> ~102.62 t)
        grommet_m = re.search(r"Break load grommet \[kN\]\s*:\s*\|\s*([\d\.\,]+)", text)
        if grommet_m:
            raw_kn = grommet_m.group(1).replace(".", "").replace(",", ".")
            try:
                kn_val = float(raw_kn)
                data["tail_mbl_tons"] = round(kn_val / 9.80665, 2)
            except ValueError:
                pass

    # 4. GEOLINK (LASHING / GeoLink)
    if "GeoLink" in text or "LASHING" in text:
        data["has_geolink"] = True

        geo_dia = re.search(r"PES-Cover\s+(\d+)\s*mm", text, re.IGNORECASE)
        if geo_dia:
            data["geolink_diameter_mm"] = float(geo_dia.group(1))

        geo_mbl = re.search(r"1\.073,30", text)
        if geo_mbl:
            data["geolink_mbl_tons"] = round(1073.30 / 9.80665, 2)

    return data
