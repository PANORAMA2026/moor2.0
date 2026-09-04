"""Generic, manufacturer-independent extraction of rope certificate facts."""
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
        return next((f.value for f in self.fields if f.name == name), None)
    def field(self, name: str):
        return next((f for f in self.fields if f.name == name), None)

def _num(s: str) -> float:
    s = re.sub(r"[^0-9,.-]", "", str(s))
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    elif "," in s:
        tail = s.rsplit(",", 1)[1]
        s = s.replace(",", "") if len(tail) == 3 else s.replace(",", ".")
    return float(s)

def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip(" :\t")

def _add(r, name, value, source, unit=None, confidence=.95):
    if value is not None:
        r.fields.append(ExtractedField(name, value, _clean(source), confidence, None, unit))

def _first(text, patterns):
    for p in patterns:
        m = re.search(p, text, re.I | re.M | re.S)
        if m:
            return m.group(1), m.group(0)
    return None, None

def _extract(text: str, certificate_type: str) -> CertificateExtraction:
    r = CertificateExtraction(certificate_type=certificate_type, raw_text=text)
    # Identification. Product Identification Code is a physical rope identifier,
    # whereas certificate number is the document identifier; retain both.
    aliases = {
        "certificate_id": [r"certificate\s*(?:no\.?|number)\s*[:#]?\s*([A-Z0-9][A-Z0-9./_-]*)"],
        "component_id": [
            r"unique\s+id[- ]?number\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",
            r"product\s+identification\s+code\s*\(\s*PIC\s*\)\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",
            r"(?:rope|product|item)\s+identification(?:\s+code)?\s*[:=]\s*([A-Z0-9][A-Z0-9._/-]*)",
            r"(?:serial|unique|rope)\s*(?:no\.?|number|id)\s*[:#=]\s*([A-Z0-9][A-Z0-9._/-]*)",
        ],
        "manufacturer": [r"(?:manufacturer|producer)\s*[:=]\s*([^\n]+)", r"examination\s+performed\s+by\s*[:=]\s*([^\n]+)"],
        "product": [r"product\s*[:=]\s*([^\n]+)", r"description\s*[:=]\s*([^\n]+)"],
        "diameter_mm": [
            r"(?:nominal\s+)?diam(?:eter)?\s*(?:\(\s*mm\s*\))?\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*mm\b",
            r"(?:nominal\s+)?diam(?:eter)?[^\n]{0,30}?\b(\d+(?:[.,]\d+)?)\s*mm\b",
        ],
        "length_m": [
            r"length\s*\(?(?:m|mtr|metres?)\)?\s*[:=]\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m",
            r"length\s*\(?(?:m|mtr|metres?)\)?\s*[:=]\s*(\d+(?:[.,]\d+)?)\s*m",
            r"quantity\s*[:=]\s*\d+\s*[x×]\s*(\d+(?:[.,]\d+)?)\s*m",
            r"\bCL\s*(\d+(?:[.,]\d+)?)\s*MTR\b",
        ],
        "minimum_breaking_load_kn": [r"minimum\s+breaking\s+load[^\n]{0,90}?([\d.,]+)\s*kN\b", r"min(?:imum)?\s+breaking\s+load[^\n]{0,40}?([\d.,]+)\s*kN\b"],
        "calculated_breaking_load_kn": [r"calculated\s+breaking\s+load[^\n]{0,90}?([\d.,]+)\s*kN\b"],
        "ldbf_kn": [r"(?:line|tail)\s*/?\s*design\s+break\s+force\s*\(?(?:ldbf|tdbf)[^\n]{0,60}?([\d.,]+)\s*kN\b", r"\bLDBF\b[^\n]{0,35}?([\d.,]+)\s*kN\b"],
        "tdbf_kn": [r"\bTDBF\b[^\n]{0,35}?([\d.,]+)\s*kN\b"],
    }
    for name, patterns in aliases.items():
        value, source = _first(text, patterns)
        if value is None: continue
        if name.endswith("_kn") or name in {"diameter_mm", "length_m"}:
            _add(r, name, _num(value), source, "kN" if name.endswith("_kn") else ("mm" if name=="diameter_mm" else "m"))
        else:
            _add(r, name, _clean(value), source)

    # Lankhorst commonly puts LDBF/TDBF in one cell as "900 kN / 91.7 Mt".
    m = re.search(r"spliced\s*-\s*line/tail\s+design\s+break\s+force[^\n]*?([\d.,]+)\s*kN\s*/\s*([\d.,]+)\s*(?:Mt|t)\b", text, re.I)
    if m:
        if r.get("ldbf_kn") is None: _add(r, "ldbf_kn", _num(m.group(1)), m.group(0), "kN", .98)
        if r.get("tdbf_kn") is None: _add(r, "tdbf_kn", _num(m.group(1)), m.group(0), "kN", .98)

    # Useful declared characteristics.
    for name, patterns in {
        "number_of_strands": [r"number\s+of\s+strands\s*[:=]\s*(\d+)"],
        "tcll_pct": [r"TCLL\s+value\s*[:=]\s*([\d.,]+)\s*%"],
        "elongation_at_break_pct": [r"elongation\s+at\s+break[^\n]*?([\d.,]+)\s*%"],
    }.items():
        value, source = _first(text, patterns)
        if value is not None: _add(r, name, _num(value), source, "%")

    # Explicit presentation/application cues. Do not infer a weak link here.
    if re.search(r"endless|grommet|loop", text, re.I): _add(r, "presentation_hint", "ENDLESS/LOOP", "presentation terminology", None, .80)
    if re.search(r"spliced\s+(?:both\s+ends|one\s+end)|spliced\s*-\s*line", text, re.I): _add(r, "presentation_hint", "SPLICED", "presentation terminology", None, .80)

    # Preserve the first source for each normalized field and warn on conflicts.
    unique={}
    for f in r.fields:
        if f.name not in unique: unique[f.name]=f
        elif unique[f.name].value != f.value: r.warnings.append(f"Ambiguous extraction for {f.name}: conflicting values {unique[f.name].value!r} and {f.value!r}")
    r.fields=list(unique.values())
    return r

def parse_certificate_text(text: str, certificate_type: str="AUTO") -> CertificateExtraction:
    text=text or ""
    if certificate_type=="AUTO":
        certificate_type="MOORING_TAIL" if re.search(r"\b(?:tail|tdbf)\b", text, re.I) else "MOORING_LINE"
    return _extract(text, certificate_type)

def validate_extraction(extraction: CertificateExtraction) -> list[str]:
    errors=[]
    # Generic parser does not impose manufacturer-specific required fields.
    # It reports missing core engineering data without pretending every form has the same fields.
    for name, label in (("component_id","physical rope/component ID"),("diameter_mm","diameter"),("length_m","length")):
        if extraction.get(name) is None: errors.append(f"{label} not extracted")
    if extraction.get("minimum_breaking_load_kn") is None and extraction.get("ldbf_kn") is None:
        errors.append("No declared breaking-load value extracted")
    return errors

def extract_pdf_text(pdf_path: str|Path):
    path=Path(pdf_path)
    if not path.exists(): raise FileNotFoundError(path)
    import fitz
    with fitz.open(path) as doc:
        pages=[p.get_text("text") or "" for p in doc]
    return "\n\n".join(pages), sum(bool(p.strip()) for p in pages), len(pages), "pymupdf", []

def parse_certificate_pdf(pdf_path: str|Path, certificate_type: str="AUTO") -> CertificateExtraction:
    text,n,total,method,warnings=extract_pdf_text(pdf_path)
    r=parse_certificate_text(text, certificate_type)
    r.pages_with_text=n; r.total_pages=total; r.extraction_method=method; r.warnings=warnings+r.warnings
    return r
