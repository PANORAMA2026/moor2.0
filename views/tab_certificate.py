def extract_text_from_pdf(pdf_file):
    try:
        reader = PdfReader(pdf_file)
        extracted_text = ""
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
        return extracted_text
    except Exception as e:
        st.error(f"Errore nella lettura del PDF: {e}")
        return ""


def extract_field_by_anchors(text: str, keywords: list) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for kw in keywords:
            if kw.lower() in line.lower():
                match = re.search(r"[:=\-]\s*(.+)", line)
                if match and match.group(1).strip():
                    return match.group(1).strip()
                if i + 1 < len(lines) and lines[i + 1].strip():
                    return lines[i + 1].strip()
    return None


def parse_certificate_text(text: str) -> dict:
    data = {
        "cert_id": None,
        "manufacturer": None,
        "material": None,
        "diameter_mm": None,
        "mbl_tons": None,
        "length_m": None,
        "standard": None,
    }

    if not text:
        return data

    raw_cert = extract_field_by_anchors(text, [
        "Certificate No",
        "Cert. No",
        "Certificate Number",
        "Certificato N",
        "Test Certificate",
        "Cert No",
    ])
    if raw_cert:
        match = re.search(r"([A-Za-z0-9\-/]+)", raw_cert)
        if match:
            data["cert_id"] = match.group(1)

    raw_mfg = extract_field_by_anchors(text, [
        "Manufacturer",
        "Costruttore",
        "Maker",
        "Producer",
        "Factory",
        "Issued by",
    ])
    if raw_mfg:
        data["manufacturer"] = raw_mfg.split("\t")[0].strip()

    mat_match = re.search(
        r"\b(HMPE|Dyneema|Polyester|Polypropylene|Nylon|Wire|Steel|Aramid|Kevlar|Polyamide)\b",
        text,
        re.IGNORECASE,
    )
    if mat_match:
        data["material"] = mat_match.group(1).upper()

    dia_raw = extract_field_by_anchors(
        text, ["Diameter", "Diametro", "Dia.", "Size"]
    )
    if dia_raw:
        num_match = re.search(r"(\d+(?:[\.,]\d+)?)", dia_raw)
        if num_match:
            data["diameter_mm"] = float(num_match.group(1).replace(",", "."))
    else:
        dia_match = re.search(r"(\d+(?:[\.,]\d+)?)\s*mm\b", text, re.IGNORECASE)
        if dia_match:
            data["diameter_mm"] = float(dia_match.group(1).replace(",", "."))

    mbl_raw = extract_field_by_anchors(text, [
        "MBL",
        "Breaking Load",
        "Carico di Rottura",
        "Minimum Breaking Load",
        "MBF",
    ])

    if mbl_raw:
        val_match = re.search(r"(\d+(?:[\.,]\d+)?)", mbl_raw)
        if val_match:
            val = float(val_match.group(1).replace(",", "."))
            if re.search(r"kN\b", mbl_raw, re.IGNORECASE):
                data["mbl_tons"] = round(val * KN_TO_TONS, 2)
            elif re.search(r"(Tons|MT|\bt\b)", mbl_raw, re.IGNORECASE):
                data["mbl_tons"] = val

    if data["mbl_tons"] is None:
        mbl_kn_match = re.search(
            r"(?:MBL|Breaking Load|Carico)\D{0,15}(\d+(?:[\.,]\d+)?)\s*kN\b",
            text,
            re.IGNORECASE,
        )
        mbl_t_match = re.search(
            r"(?:MBL|Breaking Load|Carico)\D{0,15}(\d+(?:[\.,]\d+)?)\s*(?:Tons|t|MT)\b",
            text,
            re.IGNORECASE,
        )

        if mbl_kn_match:
            data["mbl_tons"] = round(
                float(mbl_kn_match.group(1).replace(",", ".")) * KN_TO_TONS, 2
            )
        elif mbl_t_match:
            data["mbl_tons"] = float(mbl_t_match.group(1).replace(",", "."))

    std_match = re.search(
        r"\b(MEG4|ISO\s*\d+|DNV\b|DNV-GL|Lloyd'?s(?:\s*Register)?|ABS\b|BV\b|ClassNK)\b",
        text,
        re.IGNORECASE,
    )
    if std_match:
        data["standard"] = std_match.group(1)

    return data
