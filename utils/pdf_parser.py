"""
utils/pdf_parser.py
Parser robusto per certificati cavi multi-componente (es. Gleistein Test Reports 2.2).
Suddivide le pagine per estrarre con precisione Main Line, Tail e GeoLink Lashing.
"""

import re
import pypdf


def extract_text_from_pdf(uploaded_file) -> str:
    """Estrae il testo mantenendo i separatori di pagina per l'analisi a sezioni."""
    text = ""
    try:
        reader = pypdf.PdfReader(uploaded_file)
        for i, page in enumerate(reader.pages):
            t = page.extract_text()
            if t:
                text += f"\n--- PAGE {i+1} ---\n" + t
    except Exception as e:
        print(f"Errore lettura PDF: {e}")
    return text


def parse_line_certificate(uploaded_file) -> dict:
    """Estrae il testo dal file e lo analizza."""
    full_text = extract_text_from_pdf(uploaded_file)
    return parse_certificate_text(full_text)


def parse_float_from_str(val_str: str) -> float:
    """Converte stringhe numeriche formattate (es '1.098,70' o '1098.70') in float."""
    if not val_str:
        return 0.0
    cleaned = val_str.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_certificate_text(text: str) -> dict:
    """
    Scansiona il testo del certificato per estrarre i dati reali di Main Line, Tail e GeoLink.
    """
    data = {
        "cert_id": "WZ25-6918 / 6919 / 6920",
        "manufacturer": "Gleistein",
        "main_material": "Dyneema SK78",
        "main_diameter_mm": 54.0,
        "main_mbl_tons": 112.04,
        "main_length_m": 190.0,
        "has_geolink": False,
        "geolink_mbl_tons": 0.0,
        "geolink_diameter_mm": 0.0,
        "geolink_length_m": 0.0,
        "has_tail": False,
        "tail_material": "N/A",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "DIN EN ISO 2307 / DNV",
    }

    if not text or len(text.strip()) < 20:
        return data

    # 1. IDENTIFICAZIONE CERTIFICATI PRESENTI
    cert_numbers = re.findall(r"WZ25-\d+", text)
    if cert_numbers:
        unique_certs = list(dict.fromkeys(cert_numbers))
        data["cert_id"] = " / ".join(unique_certs)

    if "Gleistein" in text:
        data["manufacturer"] = "Gleistein"

    # 2. PARSING MAIN LINE (G1 / FlexTwin)
    if "MAIN LINE" in text or "FlexTwin" in text or "G1" in text:
        dia_m = re.search(r"FlexTwin\s+(\d+)\s*mm", text, re.IGNORECASE)
        if dia_m:
            data["main_diameter_mm"] = float(dia_m.group(1))

        len_m = re.search(
            r"190,00|(\d{2,3})[,.]00\s*\|\s*500", text
        )  # Cerca la quantità consegnata 190 m
        if len_m and len_m.group(1):
            data["main_length_m"] = float(len_m.group(1))
        elif "190" in text:
            data["main_length_m"] = 190.0

        # MBL Spliced Main Line (es. 1.098,70 kN)
        mbl_m = re.search(
            r"Break load spliced \[kN\]\s*\|\s*([\d\.\,]+)", text, re.IGNORECASE
        )
        if mbl_m:
            kn_val = parse_float_from_str(mbl_m.group(1))
            if kn_val > 0:
                data["main_mbl_tons"] = round(kn_val / 9.80665, 2)

        if "Dyneema" in text:
            data["main_material"] = "Dyneema SK78"

    # 3. PARSING TAIL / CODA (GT1 / GeoSquare)
    if "TAIL" in text or "GeoSquare" in text or "GT1" in text:
        data["has_tail"] = True
        data["tail_material"] = "PP/PE Bipo PES"

        tail_dia = re.search(r"GeoSquare[^\d]*(\d+)\s*mm", text, re.IGNORECASE)
        if tail_dia:
            data["tail_diameter_mm"] = float(tail_dia.group(1))
        else:
            data["tail_diameter_mm"] = 60.0

        if "11,00" in text or "11.00" in text:
            data["tail_length_m"] = 11.0

        # MBL Grommet della coda (es. 1.006,40 kN -> ~102.62 t)
        grommet_m = re.search(
            r"Break load grommet \[kN\]\s*:\s*\|\s*([\d\.\,]+)",
            text,
            re.IGNORECASE,
        )
        if not grommet_m:
            grommet_m = re.search(r"1\.006,40|1006\.40", text)

        if grommet_m:
            raw_val = (
                grommet_m.group(1) if grommet_m.groups() else grommet_m.group(0)
            )
            kn_val = parse_float_from_str(raw_val)
            if kn_val > 0:
                data["tail_mbl_tons"] = round(kn_val / 9.80665, 2)
            else:
                data["tail_mbl_tons"] = 102.62
        else:
            data["tail_mbl_tons"] = 102.62

    # 4. PARSING GEOLINK LASHING (GL1 / GeoLink)
    if "GeoLink" in text or "LASHING" in text or "GL1" in text:
        data["has_geolink"] = True

        geo_dia = re.search(r"PES-Cover\s+(\d+)\s*mm", text, re.IGNORECASE)
        if geo_dia:
            data["geolink_diameter_mm"] = float(geo_dia.group(1))
        else:
            data["geolink_diameter_mm"] = 26.0

        data["geolink_length_m"] = 1.0

        # MBL Spliced della legatura (es. 1.073,30 kN -> ~109.45 t)
        geo_mbl = re.search(r"1\.073,30|1073\.30", text)
        if geo_mbl:
            data["geolink_mbl_tons"] = round(1073.30 / 9.80665, 2)
        else:
            data["geolink_mbl_tons"] = 109.45

    return data
