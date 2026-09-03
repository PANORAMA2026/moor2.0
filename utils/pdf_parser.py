"""Certificate PDF extraction with text-first parsing and local OCR fallback.

OCR is local and deterministic; no AI API key is required. OCR output remains
unverified until the operator reviews it. Certificate terminology is preserved:
MBL and manufacturer-calculated breaking load are not silently relabelled as
LDBF unless the source explicitly says LDBF.
"""
from __future__ import annotations
import io
import os
import re
import shutil
from typing import Any
try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False
try:
    import pytesseract
    from PIL import Image, ImageOps, ImageFilter
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
from core.certificate_parser import parse_certificate_text as _parse_core_certificate

def extract_bytes_from_file(uploaded_file) -> bytes:
    if uploaded_file is None: return b""
    try:
        if hasattr(uploaded_file, "getvalue"): return uploaded_file.getvalue()
        if hasattr(uploaded_file, "read"):
            uploaded_file.seek(0); data = uploaded_file.read(); uploaded_file.seek(0); return data
    except Exception: return b""
    return b""

def extract_text_from_pdf(uploaded_file) -> str:
    data = extract_bytes_from_file(uploaded_file)
    if not data or not HAS_PYMUPDF: return ""
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            return "\n".join(page.get_text("text") for page in doc).strip()
    except Exception: return ""

def _tesseract_available() -> bool:
    if not HAS_OCR: return False
    configured = os.environ.get("TESSERACT_CMD", "").strip()
    if configured and os.path.exists(configured):
        pytesseract.pytesseract.tesseract_cmd = configured; return True
    return bool(shutil.which("tesseract"))

def extract_ocr_text_from_pdf(uploaded_file) -> tuple[str, str | None]:
    data = extract_bytes_from_file(uploaded_file)
    if not data: return "", "No PDF bytes received."
    if not HAS_PYMUPDF: return "", "PyMuPDF is not installed."
    if not HAS_OCR: return "", "Python OCR wrapper is not installed (pytesseract/Pillow)."
    if not _tesseract_available(): return "", "Tesseract executable is not installed in the Streamlit runtime."
    chunks: list[str] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
                image = ImageOps.autocontrast(image).filter(ImageFilter.SHARPEN)
                right = image.crop((int(image.width * 0.45), 0, image.width, image.height))
                candidates: list[str] = []
                for source in (right, image):
                    for psm in (3, 6, 11):
                        try:
                            text = pytesseract.image_to_string(source, lang="eng", config=f"--psm {psm}")
                            if text and text.strip(): candidates.append(text.strip())
                        except Exception: pass
                def score(s: str) -> int:
                    low = s.lower(); keys = ("diameter", "breaking load", "calculated", "quantity", "unique id", "rope type")
                    return len(s) + 500 * sum(k in low for k in keys)
                ranked = sorted(candidates, key=score, reverse=True)
                selected: list[str] = []
                for candidate in ranked:
                    if candidate not in selected: selected.append(candidate)
                    if len(selected) >= 2: break
                chunks.extend(selected)
    except Exception as exc:
        return "", f"Tesseract OCR failed: {type(exc).__name__}: {exc}"
    text = "\n\n".join(chunks).strip()
    return text, None if text else "Tesseract completed but returned no readable text."

def _field(extraction, name: str, default: Any = None):
    value = extraction.get(name); return default if value is None else value

def _kn_or_tons_to_tons(value: float | None, unit: str | None) -> float:
    if value is None: return 0.0
    return float(value) / 9.80665 if (unit or "").lower().strip() == "kn" else float(value)

def _text_value(text: str, patterns: list[str], default: str = "") -> str:
    for pattern in patterns:
        m = re.search(pattern, text, re.I | re.M)
        if m: return m.group(1).strip() if m.lastindex else m.group(0).strip()
    return default

def _to_legacy_dict(extraction) -> dict:
    ldbf_field = next((f for f in extraction.fields if f.name == "ldbf"), None)
    ship_mbl_field = next((f for f in extraction.fields if f.name == "ship_design_mbl"), None)
    min_break_field = next((f for f in extraction.fields if f.name == "minimum_breaking_load"), None)
    calc_break_field = next((f for f in extraction.fields if f.name == "calculated_breaking_load"), None)
    ldbf_tons = _kn_or_tons_to_tons(ldbf_field.value if ldbf_field else None, ldbf_field.unit if ldbf_field else None)
    ship_mbl_tons = _kn_or_tons_to_tons(ship_mbl_field.value if ship_mbl_field else None, ship_mbl_field.unit if ship_mbl_field else None)
    minimum_breaking_load_tons = _kn_or_tons_to_tons(min_break_field.value if min_break_field else None, min_break_field.unit if min_break_field else None)
    calculated_breaking_load_tons = _kn_or_tons_to_tons(calc_break_field.value if calc_break_field else None, calc_break_field.unit if calc_break_field else None)
    text = extraction.raw_text
    cert_id = _text_value(text, [r"unique\s+id[- ]?number\s*[:=]\s*([A-Z0-9_-]+)", r"(?:certificate|cert\.?|serial)\s*(?:no\.?|number)?\s*[:#=]\s*([A-Z0-9./_-]+)"], "UNKNOWN")
    manufacturer = "Bexco" if re.search(r"\bbexco\b", text, re.I) else _text_value(text, [r"\bmanufacturer\s*[:=]\s*([^\n,;]+)"], "")
    product = _text_value(text, [r"product\s*[:=]\s*([^\n]+)"], "")
    rope_type = _text_value(text, [r"rope\s+type\s*[:=]\s*([^\n]+)"], "")
    warnings = list(extraction.warnings)
    if calc_break_field and not ldbf_field:
        warnings.append("Certificate provides a Calculated Breaking Load but does not explicitly identify it as LDBF. LDBF is left blank.")
    if minimum_breaking_load_tons:
        warnings.append("Minimum Breaking Load extracted as certificate MBL; verify against the original document before saving.")
    certificate_mbl_tons = minimum_breaking_load_tons or ship_mbl_tons
    return {
        "cert_id": cert_id, "manufacturer": manufacturer or "N/A", "main_material": product or "N/A",
        "main_diameter_mm": float(_field(extraction, "diameter_mm", 0.0)), "main_mbl_tons": certificate_mbl_tons,
        "ship_design_mbl_tons": ship_mbl_tons, "minimum_breaking_load_tons": minimum_breaking_load_tons,
        "calculated_breaking_load_tons": calculated_breaking_load_tons, "ldbf_tons": ldbf_tons,
        "main_length_m": float(_field(extraction, "length_m", 0.0)), "line_linear_density": _field(extraction, "line_linear_density", None),
        "rope_type": rope_type, "average_immediate_strain_pct": {}, "has_tail": False,
        "tail_material": "", "tail_diameter_mm": 0.0, "tail_mbl_tons": 0.0, "tail_length_m": 0.0,
        "standard": _text_value(text, [r"(EN\s*10204\s*[-–]?\s*3\.2)"], ""), "_warnings": warnings,
        "_validation_errors": [], "_source_text": text, "_extraction_method": "PyMuPDF + deterministic parser", "_requires_review": True,
    }

def parse_line_certificate(uploaded_file) -> dict | None:
    if uploaded_file is None: return None
    text = extract_text_from_pdf(uploaded_file); extraction_method = "PyMuPDF + deterministic parser"; ocr_diagnostic = None
    if not text:
        text, ocr_diagnostic = extract_ocr_text_from_pdf(uploaded_file); extraction_method = "PyMuPDF + Tesseract OCR + deterministic parser"
    if not text:
        return {"cert_id": "UNKNOWN", "_warnings": [ocr_diagnostic or "No readable text was extracted."], "_validation_errors": ["No extractable certificate text"], "_requires_review": True, "_extraction_method": "OCR_FAILED"}
    result = parse_certificate_text(text)
    if result:
        result["_extraction_method"] = extraction_method; result["_warnings"] = list(result.get("_warnings", []))
        if "Tesseract OCR" in extraction_method: result["_warnings"].append("OCR output is unverified; compare every field with the original certificate before saving.")
    return result

def parse_certificate_text(text: str) -> dict | None:
    if not text or not text.strip(): return None
    extraction = _parse_core_certificate(text); result = _to_legacy_dict(extraction); result["_validation_errors"] = []
    if result["main_mbl_tons"] <= 0: result["_validation_errors"].append("Minimum Breaking Load / certificate MBL not extracted")
    if result["main_diameter_mm"] <= 0: result["_validation_errors"].append("Diameter not extracted")
    if result["main_length_m"] <= 0: result["_validation_errors"].append("Length not extracted")
    return result

def dynamic_regex_parse(text: str) -> dict: return parse_certificate_text(text) or {}

def safe_extract_json(text_response: str) -> dict | None:
    import json
    if not text_response: return None
    cleaned = re.sub(r"```(?:json)?\s*|```", "", text_response.strip())
    try: return json.loads(cleaned)
    except Exception: return None
