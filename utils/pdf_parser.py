"""Certificate PDF extraction with text-first parsing and local OCR fallback.

The OCR layer is intentionally local and deterministic: no AI API key is
required. OCR output remains unverified until the operator reviews it.
"""
from __future__ import annotations

import io
import re
from typing import Any

try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

from core.certificate_parser import parse_certificate_text as _parse_core_certificate


def extract_bytes_from_file(uploaded_file) -> bytes:
    if uploaded_file is None:
        return b""
    try:
        if hasattr(uploaded_file, "getvalue"):
            return uploaded_file.getvalue()
        if hasattr(uploaded_file, "read"):
            uploaded_file.seek(0)
            data = uploaded_file.read()
            uploaded_file.seek(0)
            return data
    except Exception:
        return b""
    return b""


def extract_text_from_pdf(uploaded_file) -> str:
    """Extract native PDF text. Returns empty string for image-only PDFs."""
    data = extract_bytes_from_file(uploaded_file)
    if not data or not HAS_PYMUPDF:
        return ""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            pages = [page.get_text("text") for page in doc]
        return "\n".join(p for p in pages if p).strip()
    except Exception:
        return ""


def extract_ocr_text_from_pdf(uploaded_file) -> str:
    """Render PDF pages and OCR them locally with Tesseract.

    Returns an empty string when OCR dependencies or the Tesseract executable
    are unavailable. The caller can then report the exact missing capability.
    """
    data = extract_bytes_from_file(uploaded_file)
    if not data or not HAS_PYMUPDF or not HAS_OCR:
        return ""
    chunks: list[str] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                # 250-300 DPI is a good compromise for certificate scans.
                pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(image, config="--psm 6")
                if text and text.strip():
                    chunks.append(text.strip())
    except Exception:
        return ""
    return "\n\n".join(chunks).strip()


def _field(extraction, name: str, default: Any = None):
    value = extraction.get(name)
    return default if value is None else value


def _kn_or_tons_to_tons(value: float | None, unit: str | None) -> float:
    if value is None:
        return 0.0
    u = (unit or "").lower().strip()
    if u == "kn":
        return float(value) / 9.80665
    return float(value)


def _to_legacy_dict(extraction) -> dict:
    ldbf_field = next((f for f in extraction.fields if f.name == "ldbf"), None)
    mbl_field = next((f for f in extraction.fields if f.name == "ship_design_mbl"), None)
    ldbf_tons = _kn_or_tons_to_tons(
        ldbf_field.value if ldbf_field else None,
        ldbf_field.unit if ldbf_field else None,
    )
    ship_mbl_tons = _kn_or_tons_to_tons(
        mbl_field.value if mbl_field else None,
        mbl_field.unit if mbl_field else None,
    )

    material_match = re.search(r"(?:material|grade)\s*[:=]\s*([^\n,;]+)", extraction.raw_text, re.I)
    manufacturer_match = re.search(r"manufacturer\s*[:=]\s*([^\n,;]+)", extraction.raw_text, re.I)
    cert_match = re.search(r"(?:certificate|cert\.?|serial|no\.?)\s*[:#=]\s*([A-Z0-9./_-]+)", extraction.raw_text, re.I)

    strain = {}
    for f in extraction.fields:
        if f.name.startswith("average_immediate_strain_"):
            pct = f.name.split("_")[4]
            strain[pct] = f.value

    return {
        "cert_id": cert_match.group(1) if cert_match else "UNKNOWN",
        "manufacturer": manufacturer_match.group(1).strip() if manufacturer_match else "N/A",
        "main_material": material_match.group(1).strip() if material_match else "N/A",
        "main_diameter_mm": float(_field(extraction, "diameter_mm", 0.0)),
        "main_mbl_tons": ldbf_tons or ship_mbl_tons,
        "ship_design_mbl_tons": ship_mbl_tons,
        "ldbf_tons": ldbf_tons,
        "main_length_m": float(_field(extraction, "length_m", 0.0)),
        "line_linear_density": _field(extraction, "line_linear_density", None),
        "average_immediate_strain_pct": strain,
        "has_tail": False,
        "tail_material": "",
        "tail_diameter_mm": 0.0,
        "tail_mbl_tons": 0.0,
        "tail_length_m": 0.0,
        "standard": "",
        "_warnings": list(extraction.warnings),
        "_validation_errors": [],
        "_source_text": extraction.raw_text,
        "_extraction_method": "PyMuPDF + deterministic parser",
        "_requires_review": True,
    }


def parse_line_certificate(uploaded_file) -> dict | None:
    if uploaded_file is None:
        return None

    # First try embedded/native PDF text because it is more precise than OCR.
    text = extract_text_from_pdf(uploaded_file)
    extraction_method = "PyMuPDF + deterministic parser"

    # Scanned/image-only certificate: automatically fall back to local OCR.
    if not text:
        text = extract_ocr_text_from_pdf(uploaded_file)
        extraction_method = "PyMuPDF + Tesseract OCR + deterministic parser"

    if not text:
        if not HAS_OCR:
            warning = "No text extracted. PDF is likely scanned and the local OCR dependencies are not available."
        else:
            warning = "No text extracted. PDF may be scanned; OCR could not produce readable text."
        return {
            "cert_id": "UNKNOWN",
            "_warnings": [warning],
            "_validation_errors": ["No extractable PDF text"],
            "_requires_review": True,
            "_extraction_method": "OCR_FAILED" if HAS_OCR else "OCR_UNAVAILABLE",
        }

    result = parse_certificate_text(text)
    if result:
        result["_extraction_method"] = extraction_method
        result["_warnings"] = list(result.get("_warnings", []))
        result["_warnings"].append("OCR output is unverified; compare all fields with the original certificate before saving.") if "Tesseract OCR" in extraction_method else None
    return result


def parse_certificate_text(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    extraction = _parse_core_certificate(text)
    result = _to_legacy_dict(extraction)
    result["_validation_errors"] = []
    if result["ldbf_tons"] <= 0:
        result["_validation_errors"].append("LDBF not extracted")
    if result["main_diameter_mm"] <= 0:
        result["_validation_errors"].append("Diameter not extracted")
    if result["main_length_m"] <= 0:
        result["_validation_errors"].append("Length not extracted")
    return result


def dynamic_regex_parse(text: str) -> dict:
    return parse_certificate_text(text) or {}


def safe_extract_json(text_response: str) -> dict | None:
    """Legacy helper retained for callers; JSON is never treated as certified data."""
    import json
    if not text_response:
        return None
    cleaned = re.sub(r"```(?:json)?\s*|```", "", text_response.strip())
    try:
        return json.loads(cleaned)
    except Exception:
        return None
