"""Conservative extraction and validation of mooring certificates.

The parser is layered: native PDF text first, OCR second at the UI boundary,
and deterministic field extraction third. Extraction never makes a value
certified; every field retains provenance and requires operator review.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import re

@dataclass(frozen=True)
class ExtractedField:
    name: str
    value: object
    source_text: str
    confidence: float
    page: Optional[int] = None
    unit: Optional[str] = None

@dataclass
class CertificateExtraction:
    certificate_type: str = "UNKNOWN"
    fields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    pages_with_text: int = 0
    total_pages: int = 0
    extraction_method: str = "none"
    def get(self, name: str):
        for f in self.fields:
            if f.name == name:
                return f.value
        return None

FIELD_PATTERNS = {
    "ship_design_mbl": [r"ship\s+design\s+mbl\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "ldbf": [r"(?:line\s+design\s+break\s+force|ldbf)\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "diameter_mm": [r"diameter\s*[:=]?\s*([\d.,]+)\s*(mm|m)?"],
    "length_m": [r"length\s*[:=]?\s*([\d.,]+)\s*(m|meter|metre|ft)?", r"quantity\s*[:=]?\s*\d+\s*x\s*([\d.,]+)\s*m\b"],
    "line_linear_density": [r"line\s+linear\s+density\s*[:=]?\s*([\d.,]+)\s*(kg/m|kg/m2)?"],
    "tail_design_break_force": [r"(?:tail\s+design\s+break\s+force|tdbf)\s*[:=]?\s*([\d.,]+)\s*(kn|t|tonnes?|tons?)?"],
    "tail_linear_density": [r"tail\s+linear\s+density\s*[:=]?\s*([\d.,]+)"],
    "minimum_breaking_load": [r"min(?:imum)?\s+breaking\s+load\s+rope\s*[:=]?\s*([\d.,]+)\s*t\b"],
    "calculated_breaking_load": [r"calculated\s+breaking\s+load\s+rope\s*[:=]?\s*([\d.,]+)\s*t\b"],
}

def _number(s: str) -> float:
    value = s.strip().replace(" ", "")
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".")
    return float(value)

def _extract_from_text(text: str, page: int | None = None, certificate_type: str = "MOORING_LINE") -> CertificateExtraction:
    result = CertificateExtraction(certificate_type=certificate_type, raw_text=text)
    normalized = re.sub(r"[\t ]+", " ", text)
    for name, patterns in FIELD_PATTERNS.items():
        matches = []
        for pattern in patterns:
            matches.extend(re.finditer(pattern, normalized, re.I))
        if len(matches) == 1:
            m = matches[0]
            raw_unit = m.group(2) if m.lastindex and m.lastindex >= 2 else None
            result.fields.append(ExtractedField(name, _number(m.group(1)), m.group(0), 0.95, page, raw_unit))
        elif len(matches) > 1:
            vals = {_number(m.group(1)) for m in matches}
            if len(vals) == 1:
                m = matches[0]
                raw_unit = m.group(2) if m.lastindex and m.lastindex >= 2 else None
                result.fields.append(ExtractedField(name, _number(m.group(1)), m.group(0), 0.95, page, raw_unit))
            else:
                result.warnings.append(f"Ambiguous extraction for {name}: {len(matches)} matches")
    calc = result.get("calculated_breaking_load")
    if calc is not None and result.get("ldbf") is None:
        result.fields.append(ExtractedField("ldbf", calc, "calculated breaking load rope", 0.93, page, "t"))
    strain_patterns = [
        re.compile(r"%\s*(?:LDBF|TDBF)\s*[:=]?\s*(10|20|30|40|50)\s*[^\n]{0,80}?([\d.,]+)\s*%?", re.I),
        re.compile(r"(10|20|30|40|50)\s*%\s*(?:LDBF|TDBF)[^\n]{0,80}?([\d.,]+)\s*%?", re.I),
    ]
    seen = set()
    for pattern in strain_patterns:
        for m in pattern.finditer(normalized):
            pct = int(m.group(1))
            if pct in seen:
                continue
            seen.add(pct)
            basis = "tdbf" if "tdbf" in m.group(0).lower() else "ldbf"
            result.fields.append(ExtractedField(f"average_immediate_strain_{pct}_pct_{basis}", _number(m.group(2)), m.group(0), 0.88, page, "%"))
    return result

def parse_certificate_text(text: str, certificate_type: str = "MOORING_LINE") -> CertificateExtraction:
    return _extract_from_text(text, None, certificate_type)

def extract_pdf_text(pdf_path: str | Path) -> tuple[str, int, int, str, list[str]]:
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(path)
    warnings: list[str] = []
    try:
        import fitz
        doc = fitz.open(path)
        pages = [page.get_text("text") or "" for page in doc]
        doc.close()
        text = "\n\n".join(pages)
        nonempty = sum(bool(p.strip()) for p in pages)
        if nonempty:
            return text, nonempty, len(pages), "pymupdf", warnings
    except Exception as exc:
        warnings.append(f"PyMuPDF extraction failed: {exc}")
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(pages)
        nonempty = sum(bool(p.strip()) for p in pages)
        if nonempty:
            return text, nonempty, len(pages), "pypdf", warnings
        warnings.append("PDF appears image-only or contains no extractable text; OCR is required.")
        return text, 0, len(pages), "none", warnings
    except Exception as exc:
        warnings.append(f"pypdf extraction failed: {exc}")
        raise RuntimeError("Unable to extract text from PDF with available engines.") from exc

def parse_certificate_pdf(pdf_path: str | Path, certificate_type: str = "AUTO") -> CertificateExtraction:
    text, pages_with_text, total_pages, method, warnings = extract_pdf_text(pdf_path)
    if certificate_type == "AUTO":
        lower = text.lower()
        certificate_type = "MOORING_TAIL" if "tail design break force" in lower or "tdbf" in lower else "MOORING_LINE"
    result = CertificateExtraction(certificate_type=certificate_type, raw_text=text, pages_with_text=pages_with_text, total_pages=total_pages, extraction_method=method, warnings=warnings)
    if not text.strip():
        result.warnings.append("No machine-readable text found. Provide an OCR-capable workflow for scanned certificates.")
        return result
    try:
        import fitz
        doc = fitz.open(pdf_path)
        page_texts = [p.get_text("text") or "" for p in doc]
        doc.close()
    except Exception:
        page_texts = text.split("\n\n")
    for page_no, page_text in enumerate(page_texts, start=1):
        if page_text.strip():
            page_result = _extract_from_text(page_text, page_no, certificate_type)
            result.fields.extend(page_result.fields)
            result.warnings.extend(page_result.warnings)
    by_name: dict[str, list[ExtractedField]] = {}
    for f in result.fields:
        by_name.setdefault(f.name, []).append(f)
    deduped: list[ExtractedField] = []
    for name, candidates in by_name.items():
        values = {round(float(c.value), 8) for c in candidates if isinstance(c.value, (int, float))}
        if len(candidates) == 1 or len(values) == 1:
            deduped.append(candidates[0])
        else:
            result.warnings.append(f"Ambiguous extraction for {name}: conflicting values on multiple pages")
    result.fields = deduped
    return result

def validate_extraction(extraction: CertificateExtraction) -> list[str]:
    errors: list[str] = []
    required = {"ldbf", "diameter_mm", "length_m"} if extraction.certificate_type != "MOORING_TAIL" else {"tail_design_break_force"}
    present = {f.name for f in extraction.fields}
    for name in required - present:
        errors.append(f"Required field not extracted: {name}")
    for name in ("ldbf", "minimum_breaking_load", "calculated_breaking_load", "tail_design_break_force", "diameter_mm", "length_m"):
        value = extraction.get(name)
        if value is not None and value <= 0:
            errors.append(f"{name} must be greater than zero")
    if extraction.pages_with_text == 0 and not extraction.raw_text.strip():
        errors.append("No machine-readable PDF text; OCR/manual review required")
    return errors
